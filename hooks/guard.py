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


def repo_secrets() -> list[str]:
    config = Path(os.environ.get("CLAUDE_PROJECT_DIR", ".")) / ".claude" / "noemeo-guard.json"
    try:
        names = json.loads(config.read_text()).get("secrets", [])
    except (OSError, ValueError, AttributeError):
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


def check_segment(words: list[str]) -> str | None:
    # Skip leading env assignments and common wrappers.
    while words and (re.fullmatch(r"\w+=.*", words[0]) or words[0] in ("sudo", "command", "env")):
        words = words[1:]
    if not words:
        return None
    cmd, args = words[0].rsplit("/", 1)[-1], words[1:]

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
    for segment in re.split(CONTROL_RE + r"|\$\(|`", strip_prose_heredocs(command)):
        if not PROSE_RE.match(segment):
            m = SECRET_RE.search(segment)
            if m:
                deny(f"Touching secrets ({m.group(1)}) is blocked.")
        try:
            words = shlex.split(segment, comments=True)
        except ValueError:
            words = segment.split()
        reason = check_segment(words)
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
