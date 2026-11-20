#!/usr/bin/env python3
"""Stop hook: runs `pytest -x -q` in the session's repo and, if it
fails, blocks the stop and hands the failure back to Claude -- so a turn
can't end "done" while tests are red.

Only in a git repo whose .venv has pytest installed. A linked worktree
without .venv/bin/pytest whose main checkout has one -- a fresh worktree
nobody installed -- gets a one-line warning, once per session, instead
of a silent skip.

A repo can add pytest arguments in .claude/noemeo-guard.json, e.g. to
leave slow browser tests to review and CI:

    {"stop_pytest_args": ["-m", "not browser"]}

Skipped when the working tree is identical to the last state that passed
(a question-only turn, or nothing changed since the last green run),
keyed on a hash of HEAD, `git diff HEAD` and untracked files. State
lives in the git dir, per clone: claude-tests-green (hash of the last
passing tree), claude-tests-last-failure (shown by session_context.sh)
and claude-tests-skip-warned (the session last warned about no .venv).
"""

import hashlib
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pyfloor  # noqa: E402

pyfloor.check("open", "stop_tests.py")  # before anything that needs 3.12

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


def repo_pytest_args() -> list[str]:
    config = Path(".claude") / "noemeo-guard.json"
    try:
        args = json.loads(config.read_text()).get("stop_pytest_args", [])
    except (OSError, ValueError, AttributeError):
        return []
    if not isinstance(args, list) or not all(isinstance(a, str) for a in args):
        return []
    return args


def main_checkout_has_pytest() -> bool:
    common = Path(git("rev-parse", "--path-format=absolute", "--git-common-dir").strip())
    main = common.parent
    return main.resolve() != Path.cwd().resolve() and (main / ".venv" / "bin" / "pytest").exists()


def warn_once(git_dir: Path, session_id: str, message: str) -> None:
    marker = git_dir / "claude-tests-skip-warned"
    try:
        if session_id and marker.exists() and marker.read_text().strip() == session_id:
            return
        marker.write_text(session_id)
    except OSError:
        pass  # can't remember it: warn anyway
    print(json.dumps({"systemMessage": message}))


def _inside(path: Path, base: Path) -> bool:
    try:
        path.resolve().relative_to(base)
        return True
    except (OSError, ValueError):
        return False


def lint_errors() -> list[str]:
    """Decision lint errors, only when the repo configures `decision_roots`.
    Only errors about files inside the repo block; errors from roots
    outside it (a sibling checkout's decisions) are one notice line on
    stderr. An internal failure never blocks the stop."""
    try:
        config = json.loads((Path(".claude") / "noemeo-guard.json").read_text())
        roots = config.get("decision_roots")
    except (OSError, ValueError, AttributeError):
        return []
    if not roots or not isinstance(roots, list):
        return []
    try:
        import decisions

        repo = Path.cwd().resolve()
        located, _warnings = decisions.lint_corpus_located(decisions.load(repo), repo)
        blocking, outside = [], []
        for message, sources in located:
            if not sources or any(_inside(s, repo) for s in sources):
                blocking.append(message)
                continue
            named = [
                r for r in roots
                if isinstance(r, str)
                and any(_inside(s, decisions._root_dir(repo, r).resolve()) for s in sources)
            ] or [str(Path(sources[0]).parent)]
            outside.extend(r for r in named if r not in outside)
        if outside:
            print(
                f"Decision lint: errors in decision roots outside this repo "
                f"({', '.join(outside)}); run decisions.py lint in their repo.",
                file=sys.stderr,
            )
        return blocking
    except Exception as e:  # noqa: BLE001
        print(f"decisions lint failed internally ({e!r}); run decisions.py lint", file=sys.stderr)
        return []


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
    errors = lint_errors()
    if errors:
        print(
            json.dumps(
                {
                    "decision": "block",
                    "reason": "Decision lint failed (python3 hooks/decisions.py lint). "
                    "Fix these before finishing:\n\n" + "\n".join(f"error: {e}" for e in errors),
                }
            )
        )
        return
    if not Path(".venv/bin/pytest").exists():
        if main_checkout_has_pytest():
            warn_once(
                git_dir,
                payload.get("session_id", ""),
                "Stop hook: no .venv/bin/pytest in this worktree (its main checkout "
                "has one), so tests were skipped. Install its dev dependencies.",
            )
        return

    green_file = git_dir / "claude-tests-green"
    failure_file = git_dir / "claude-tests-last-failure"
    extra = repo_pytest_args()
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
                *extra,
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
                "reason": f"Tests are failing ({shlex.join(['pytest', '-x', '-q', *extra])}). "
                "Fix them, or tell the user why "
                "they can't be fixed, before finishing:\n\n" + tail,
            }
        )
    )


if __name__ == "__main__":
    main()
