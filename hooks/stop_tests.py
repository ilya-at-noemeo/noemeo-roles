#!/usr/bin/env python3
"""Stop hook: runs `pytest -x -q` in the session's repo and, if it
fails, blocks the stop and hands the failure back to Claude -- so a turn
can't end "done" while tests are red.

Only in a git repo whose .venv has pytest installed. Skipped when the
working tree is identical to the last state that passed (a question-only
turn, or nothing changed since the last green run), keyed on a hash of
HEAD, `git diff HEAD` and untracked files. State lives in the git dir,
per clone: claude-tests-green (hash of the last passing tree) and
claude-tests-last-failure (shown by session_context.sh).
"""

import hashlib
import json
import os
import subprocess
import sys
from pathlib import Path

TIMEOUT_S = 280  # under the hook's own 300s timeout


def git(*args: str) -> str:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=True).stdout


def tree_hash() -> str:
    h = hashlib.sha256()
    h.update(git("rev-parse", "HEAD").encode())
    h.update(git("diff", "HEAD", "--binary").encode())
    for name in sorted(git("ls-files", "-o", "--exclude-standard", "-z").split("\0")):
        if name and os.path.isfile(name):
            h.update(name.encode())
            h.update(Path(name).read_bytes())
    return h.hexdigest()


def main() -> None:
    payload = json.load(sys.stdin)
    # Already blocked once this stop and Claude is still stopping: let it
    # (it may be stuck, or reporting the failure to the user) rather than
    # looping forever.
    if payload.get("stop_hook_active"):
        return

    try:
        os.chdir(os.environ.get("CLAUDE_PROJECT_DIR") or ".")
        os.chdir(git("rev-parse", "--show-toplevel").strip())
        git_dir = Path(git("rev-parse", "--absolute-git-dir").strip())
    except (OSError, subprocess.CalledProcessError):
        return  # not a git repo
    if not Path(".venv/bin/pytest").exists():
        return

    green_file = git_dir / "claude-tests-green"
    failure_file = git_dir / "claude-tests-last-failure"
    current = tree_hash()
    if green_file.exists() and green_file.read_text().strip() == current:
        return

    try:
        proc = subprocess.run(
            [
                ".venv/bin/python",
                "-m",
                "pytest",
                "-x",
                "-q",
                "--no-header",
                "-p",
                "no:cacheprovider",
            ],
            capture_output=True,
            text=True,
            timeout=TIMEOUT_S,
        )
    except subprocess.TimeoutExpired:
        print(json.dumps({"systemMessage": f"Stop hook: pytest took over {TIMEOUT_S}s; skipped."}))
        return

    if proc.returncode == 0:
        green_file.write_text(current)
        failure_file.unlink(missing_ok=True)
        return
    if proc.returncode == 5:  # no tests collected
        return

    tail = "\n".join((proc.stdout + proc.stderr).strip().splitlines()[-60:])
    failure_file.write_text(tail)
    print(
        json.dumps(
            {
                "decision": "block",
                "reason": "Tests are failing (pytest -x -q). Fix them, or tell the user why "
                "they can't be fixed, before finishing:\n\n" + tail,
            }
        )
    )


if __name__ == "__main__":
    main()
