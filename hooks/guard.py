#!/usr/bin/env python3
"""PreToolUse guard: denies a few commands and paths outright, whatever
the permission mode, in every repo the plugin is enabled in.

- `rm` with both recursive and force flags.
- `git push` that force-updates the remote (--force, -f,
  --force-with-lease, or a +refspec).
- `git clean -f` in any form: it deletes untracked files, and with -x
  ignored ones too -- typically local data and secrets nothing else has.
- Reading or writing secrets, by Bash command or by file tool: .env and
  .env.* (not .env.example), *.pem, .certs/, .aws/credentials, plus any
  names the repo lists in .claude/noemeo-guard.json:

      {"secrets": [".my_tokens.json", "*.p12"]}

  (a literal file or directory name, or "*.<ext>").
- AWS calls on the wrong account, where the repo opts in by naming its
  AWS profiles in .claude/noemeo-guard.json:

      {"aws_profiles": ["acme-dev", "acme-admin"]}

  An `aws` or `terraform` command that can reach AWS must then use one
  of them, via --profile, an AWS_PROFILE= prefix, or AWS_PROFILE in the
  session's environment. Otherwise it would fall back to the default
  credentials, which on a developer's own machine may be another
  account entirely. Offline commands (`aws --version`, `terraform fmt`,
  `validate`, `version`, `init -backend=false`) are allowed.

Commit messages and PR bodies that only mention a secret's name are
allowed. Ask the user to run a denied command themselves if it's really
needed.
"""

import json
import os
import re
import shlex
import sys
from pathlib import Path

DEFAULT_SECRETS = [
    r"\.env(?!\.example\b)(?:\.[\w.-]+)?",
    r"[\w.-]*\.pem",
    r"\.certs",
    r"\.aws/credentials",
]

HEREDOC_RE = re.compile(r"<<-?\s*(['\"]?)(\w+)\1[^\n]*\n.*?\n\s*\2\s*(?=\n|$)", re.S)
# Commands whose text is prose (a commit message, a PR body), not paths.
PROSE_RE = re.compile(r"^\s*(git\s+commit|gh\s+(pr|issue)\s+(create|comment|edit))\b")
CONTROL_RE = r"&&|\|\||[;|&\n]"


def repo_config() -> dict:
    config = (
        Path(os.environ.get("CLAUDE_PROJECT_DIR", "."))
        / ".claude"
        / "noemeo-guard.json"
    )
    try:
        loaded = json.loads(config.read_text())
    except (OSError, ValueError):
        return {}
    return loaded if isinstance(loaded, dict) else {}


def repo_secrets() -> list[str]:
    names = repo_config().get("secrets", [])
    if not isinstance(names, list):
        return []
    return [
        r"[\w.-]*\." + re.escape(n[2:]) if n.startswith("*.") else re.escape(n)
        for n in names
        if isinstance(n, str) and n
    ]


SECRET_RE = re.compile(
    r"""(?:^|[\s/'"=<>:(])("""
    + "|".join(DEFAULT_SECRETS + repo_secrets())
    + r""")(?=$|[\s/'";|&)<>])"""
)


def deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason + " (noemeo plugin guard hook)",
                }
            }
        )
    )
    sys.exit(0)


def short_flags(args: list[str]) -> set[str]:
    flags = set()
    for a in args:
        if a.startswith("-") and not a.startswith("--"):
            flags.update(a[1:])
    return flags


def _aws_profiles() -> list[str]:
    value = repo_config().get("aws_profiles")
    return (
        [p for p in value if isinstance(p, str) and p]
        if isinstance(value, list)
        else []
    )


AWS_PROFILES = _aws_profiles()
TERRAFORM_OFFLINE = {
    "", "fmt", "validate", "version", "help", "get",
    "-version", "--version", "-help", "--help",
}  # fmt: skip  # fmt: skip
# The command itself changes AWS_PROFILE: the session's value can't be
# trusted for it, so each aws/terraform needs its own listed profile.
PROFILE_CHANGED_RE = re.compile(
    r"\bunset\b[^;&|\n]*\bAWS_PROFILE\b|\bAWS_PROFILE=|\benv\b[^;&|\n]*\s(-u|--unset)[= ]?AWS_PROFILE\b"
    r"|\benv\b[^;&|\n]*\s(-i|--ignore-environment)\b"
)
# Wrappers whose own flags come before the command they run.
WRAPPERS = {
    "sudo", "command", "env", "nohup", "time", "exec", "xargs",
    "if", "elif", "while", "until", "then", "do", "else", "!",
}  # fmt: skip


def check_aws_profile(
    cmd: str, args: list[str], assigned: dict[str, str], trust_env: bool
) -> str | None:
    if not AWS_PROFILES or cmd not in ("aws", "terraform"):
        return None
    if cmd == "aws" and (
        not args
        or "help" in args
        or args[0] == "--version"
        or args[:2] in (["configure", "list"], ["configure", "list-profiles"])
    ):
        return None
    if cmd == "terraform":
        sub = next((a for a in args if not a.startswith("-chdir")), "")
        rest = args[args.index(sub) + 1 :] if sub in args else []
        if (
            sub in TERRAFORM_OFFLINE
            or (sub == "init" and "-backend=false" in args)
            or (sub == "providers" and rest[:1] in (["lock"], ["mirror"]))
        ):
            return None
    named = []
    if cmd == "aws":  # terraform has no --profile flag
        named = [args[i + 1] for i, a in enumerate(args[:-1]) if a == "--profile"]
        named += [a.split("=", 1)[1] for a in args if a.startswith("--profile=")]
    if named:
        profile = named[-1]
    elif "AWS_PROFILE" in assigned:
        profile = assigned["AWS_PROFILE"]
    else:
        profile = os.environ.get("AWS_PROFILE") if trust_env else None
    if profile in AWS_PROFILES:
        return None
    how = (
        "add --profile <profile>"
        if cmd == "aws"
        else "prefix it with AWS_PROFILE=<profile>"
    )
    return (
        f"{cmd} without one of this repo's AWS profiles ({', '.join(AWS_PROFILES)}) would use "
        f"the default credentials, which may be another account: {how}."
    )


def check_segment(words: list[str], trust_env: bool = True) -> str | None:
    # Skip subshell/group openers, leading env assignments and wrappers
    # (with their flags) to find the command that actually runs.
    assigned: dict[str, str] = {}
    while words:
        first = words[0].lstrip("({")
        if not first:
            words = words[1:]
        elif re.fullmatch(r"\w+=.*", first):
            key, value = first.split("=", 1)
            assigned[key] = value
            words = words[1:]
        elif first in WRAPPERS or first == "timeout":
            words = words[1:]
            while words and words[0].startswith("-"):
                words = (
                    words[2:]
                    if words[0] in ("-u", "-s", "-k", "-n", "-I")
                    else words[1:]
                )
            if first == "timeout" and words:
                words = words[1:]  # the duration
        else:
            words = [first, *words[1:]]
            break
    if not words:
        return None
    cmd, args = words[0].rsplit("/", 1)[-1], words[1:]

    reason = check_aws_profile(cmd, args, assigned, trust_env)
    if reason:
        return reason

    if cmd == "rm":
        flags = short_flags(args)
        recursive = "r" in flags or "R" in flags or "--recursive" in args
        force = "f" in flags or "--force" in args
        if recursive and force:
            return "rm -rf is blocked."

    if cmd == "git" and args:
        # Skip git's own options (-C dir, -c k=v) to find the subcommand.
        i = 0
        while i < len(args) and args[i].startswith("-"):
            i += 2 if args[i] in ("-C", "-c") else 1
        sub, rest = (args[i], args[i + 1 :]) if i < len(args) else ("", [])
        if sub == "push" and (
            any(a.startswith("--force") for a in rest)
            or "f" in short_flags(rest)
            or any(a.startswith("+") for a in rest)
        ):
            return "Force-pushing is blocked."
        if sub == "clean" and ("f" in short_flags(rest) or "--force" in rest):
            return (
                "git clean -f is blocked: it deletes untracked (and with -x, ignored) "
                "files, often local data or secrets with no other copy."
            )
    return None


def strip_prose_heredocs(command: str) -> str:
    """Drops the body of a heredoc that feeds a commit message or PR
    body -- mentioning a secret's name there isn't touching it."""

    def repl(m: re.Match) -> str:
        # The simple command the heredoc feeds: the text since the last
        # control operator before `<<`.
        feeding = re.split(CONTROL_RE, command[: m.start()])[-1]
        return "<<HEREDOC" if PROSE_RE.match(feeding) else m.group(0)

    return HEREDOC_RE.sub(repl, command)


def check_bash(command: str) -> None:
    trust_env = not PROFILE_CHANGED_RE.search(command)
    for segment in re.split(CONTROL_RE + r"|\$\(|`", strip_prose_heredocs(command)):
        if not PROSE_RE.match(segment):
            m = SECRET_RE.search(segment)
            if m:
                deny(f"Touching secrets ({m.group(1)}) is blocked.")
        try:
            words = shlex.split(segment, comments=True)
        except ValueError:
            words = segment.split()
        reason = check_segment(words, trust_env)
        if reason:
            deny(reason)


def main() -> None:
    payload = json.load(sys.stdin)
    tool_input = payload.get("tool_input") or {}
    if payload.get("tool_name") == "Bash":
        check_bash(tool_input.get("command", ""))
        return
    for key in ("file_path", "path", "notebook_path", "glob"):
        value = tool_input.get(key)
        if value:
            m = SECRET_RE.search(value)
            if m:
                deny(f"Touching secrets ({m.group(1)}) is blocked.")


if __name__ == "__main__":
    main()
