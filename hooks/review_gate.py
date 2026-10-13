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


def _repo_and_base(command: str, cwd: Path) -> tuple[Path | None, str | None]:
    where = cwd
    m = re.match(r"\s*cd\s+(\"[^\"]+\"|'[^']+'|\S+)\s*&&", command)
    if m:
        where = (cwd / shlex.split(m.group(1))[0]).resolve()
    repo = toplevel(where)
    base = None
    try:
        words = shlex.split(command[command.index("gh pr create") :])
    except ValueError:
        words = command.split()
    for i, w in enumerate(words):
        if w in ("--base", "-B") and i + 1 < len(words):
            base = words[i + 1]
        elif w.startswith("--base="):
            base = w.split("=", 1)[1]
    if repo is None:
        return None, None
    if base:
        return repo, base if base.startswith("origin/") else f"origin/{base}"
    bases = candidate_bases(repo)
    return repo, bases[0] if bases else None


def main() -> None:
    event = json.load(sys.stdin)
    if event.get("tool_name") != "Bash":
        return
    command = (event.get("tool_input") or {}).get("command", "")
    if "gh pr create" not in command:
        return
    repo, base = _repo_and_base(command, Path(event.get("cwd") or "."))
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
