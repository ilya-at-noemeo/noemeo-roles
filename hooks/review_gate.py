#!/usr/bin/env python3
"""PreToolUse hook: before `gh pr create`, require a noemeo-code-reviewer
review of the change as it is now.

Looks up the repo the command runs in (a leading `cd <dir> &&`, else the
session's working directory), its PR base (`--base`/`-B`, else the
remote's default branch, or dev where it exists), and the fingerprint of
the change against that base (review_state.py). Allows the command when
the latest review with that fingerprint is "Ready" or "Ready with nits";
denies it otherwise, telling Claude what to do. Anything this hook can't
work out (not a git repo, unknown base) is let through rather than
guessed.

Fails closed: any `gh pr create` in the command counts, unless it sits in
a heredoc body or a quoted string and nothing in the command could run
that text: no shell or interpreter (`bash -c`, `| sh`, `python3 - <<EOF`,
`eval`, ...), no `$VAR` or script path as a command, and no `$(...)` or
backtick before it. So `git commit -m '...'` or `git commit -F - <<'EOF'`
mentioning it passes, while anything this can't rule out costs a false
denial, never a PR without a review.
"""

import json
import re
import shlex
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ beside the hooks
sys.path.insert(0, str(Path(__file__).parent))
from review_state import candidate_bases, latest, toplevel  # noqa: E402


def _deny(reason: str) -> None:
    print(
        json.dumps(
            {
                "hookSpecificOutput": {
                    "hookEventName": "PreToolUse",
                    "permissionDecision": "deny",
                    "permissionDecisionReason": reason,
                }
            }
        )
    )


# `gh pr new` is gh's own alias for `gh pr create`.
PHRASE = re.compile(r"(?<![\w-])['\"]?gh(\.exe)?['\"]?\s+['\"]?pr['\"]?\s+['\"]?(create|new)\b")
SEPARATORS = {";", "&&", "||", "|", "&", "(", ")", ";;", "\n"}
# Anything that could run quoted or heredoc text as a command: shells and
# interpreters (`bash -c`, `cat <<EOF | sh`, `python3 - <<EOF`), other
# runners, a `$VAR`, a script path or any quoted word (`"$SHELL"`) in
# command position. Their mere presence anywhere makes every mention count.
RUNNERS = re.compile(
    r"(^|[^\w.-])(sh|bash|zsh|dash|ksh|csh|tcsh|fish|eval|source|exec|python[\d.]*|node|deno"
    r"|bun|perl|ruby|php|osascript|awk|gawk|make|trap|tmux|screen|expect|script|su|sudo|watch"
    r"|parallel|xargs|ssh|env|pwsh|powershell|cmd|npx|lua|Rscript|tclsh)(?![\w.-])"
    r"|(^|[;&|(\n]\s*)(\w+=\S*\s+)*(\.\s|\$|\./|/|~/|['\"])|-c\s+alias\.|rebase\b[^\n;&|]*\s(-x|--exec)\b"
)
HEREDOC_OP = re.compile(r"<<(-?)[ \t]*(['\"]?)([A-Za-z_][\w.-]*)\2")


def _contexts(command: str) -> list[str]:
    """Per character: "code", "sq", "dq" or "heredoc" (a heredoc body). An
    unterminated quote is left as code: assume the worst."""
    n = len(command)
    kind = ["code"] * n
    state, span = None, 0
    pending: list[tuple[str, bool]] = []  # heredocs opened on this line: delimiter, `<<-`
    i = 0
    while i < n:
        c = command[i]
        if state is None:
            if c == "\\":
                i += 2
                continue
            if c == "#" and (i == 0 or command[i - 1] in " \t\n;&|()"):
                eol = command.find("\n", i)  # a comment: code to end of line, opens nothing
                i = n if eol < 0 else eol
                continue
            if command.startswith("$'", i):  # ANSI-C quoting: backslash escapes
                state, span = "$'", i
                kind[i : i + 2] = ["sq", "sq"]
                i += 2
                continue
            if c in "'\"":
                state, span = c, i
                kind[i] = "sq" if c == "'" else "dq"
                i += 1
                continue
            elif command.startswith("<<<", i):  # a here-string, not a heredoc
                i += 3
                continue
            elif command.startswith("<<", i):
                line = command[command.rfind("\n", 0, i) + 1 : i]
                m = HEREDOC_OP.match(command, i)
                if m and line.count("((") <= line.count("))"):
                    pending.append((m.group(3), m.group(1) == "-"))
                    i = m.end()
                    continue
            elif c == "\n" and pending:
                i += 1
                for delim, strip in pending:
                    while i < n:
                        eol = command.find("\n", i)
                        eol = n if eol < 0 else eol
                        text = command[i:eol]
                        if (text.lstrip("\t") if strip else text) == delim:
                            i = eol + 1
                            break
                        kind[i:eol] = ["heredoc"] * (eol - i)
                        i = eol + 1
                pending = []
                continue
        elif c == "\\" and state in ('"', "$'"):
            kind[i : i + 2] = ["dq" if state == '"' else "sq"] * len(kind[i : i + 2])
            i += 2
            continue
        else:
            kind[i] = "dq" if state == '"' else "sq"
            if c == state[-1]:
                state = None
        i += 1
    if state is not None:
        kind[span:] = ["code"] * (n - span)
    return kind


def _pr_create_args(command: str) -> list[str] | None:
    """The arguments of the first `gh pr create`/`new` in the command that could
    run, else None. Fails closed: a mention counts unless it is provably
    inert -- in a heredoc body or a quoted string that nothing would run."""
    if not PHRASE.search(command):
        return None
    kind = _contexts(command)
    code = "".join(  # unquoted text, plus each opening quote so a quoted command word is seen
        c if k == "code" or (k != "heredoc" and (j == 0 or kind[j - 1] == "code")) else " "
        for j, (c, k) in enumerate(zip(command, kind))
    )
    runner = bool(RUNNERS.search(code))  # a runner only acts from unquoted text
    for m in PHRASE.finditer(command):
        before = command[: m.start()]
        unquoted = any(kind[j] == "code" for j in range(m.start(), m.end()))
        if unquoted or runner or "$(" in before or "`" in before:
            ends = (j for j in range(m.end(), len(command)) if command[j] == "\n" and kind[j] == "code")
            eol = next((j for j in ends if command[j - 1] != "\\"), None)
            rest = command[m.end() : eol].replace("\\\n", " ")
            try:
                lexer = shlex.shlex(rest, posix=True, punctuation_chars=True)
                lexer.whitespace_split, lexer.commenters = True, ""
                words = list(lexer)
            except ValueError:
                words = rest.split()
            end = next((j for j, w in enumerate(words) if w in SEPARATORS), len(words))
            return words[:end]
    return None


def _repo_and_base(command: str, args: list[str], cwd: Path) -> tuple[Path | None, str | None]:
    where = cwd
    m = re.match(r"\s*cd\s+(\"[^\"]+\"|'[^']+'|\S+)\s*&&", command)
    if m:
        where = (cwd / shlex.split(m.group(1))[0]).resolve()
    repo = toplevel(where)
    base = None
    words = args
    for i, w in enumerate(words):
        if w in ("--base", "-B") and i + 1 < len(words):
            base = words[i + 1]
        elif w.startswith("--base="):
            base = w.split("=", 1)[1]
    if repo is None:
        return None, None
    base = (base or "").rstrip(")'\"`;")  # e.g. `main'` from inside `bash -c '...'`
    if base:
        return repo, base if base.startswith("origin/") else f"origin/{base}"
    bases = candidate_bases(repo)
    return repo, bases[0] if bases else None


def main() -> None:
    event = json.load(sys.stdin)
    if event.get("tool_name") != "Bash":
        return
    command = (event.get("tool_input") or {}).get("command", "")
    args = _pr_create_args(command)
    if args is None:
        return
    repo, base = _repo_and_base(command, args, Path(event.get("cwd") or "."))
    if repo is None or base is None:
        return
    review = latest(repo, base)
    if review and review.get("verdict") in ("Ready", "Ready with nits"):
        return
    if review:
        _deny(
            f"The last noemeo-code-reviewer review of this exact change in {repo} said "
            f"\"{review.get('verdict')}\": {review.get('summary', '')}\n"
            "Fix its findings, then have noemeo-code-reviewer review the change again "
            "before opening the PR."
        )
        return
    _deny(
        f"No noemeo-code-reviewer review matches the change in {repo} against {base} as it "
        "is now (none yet, or the code changed since). Run the noemeo-code-reviewer agent on "
        f"this branch against {base.removeprefix('origin/')}, naming the repo by its absolute "
        "path; then open the PR. A verdict of Ready or Ready with nits lets it through."
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 -- a broken gate must not wedge the session
        print(f"review_gate: {e}", file=sys.stderr)
