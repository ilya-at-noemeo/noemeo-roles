#!/usr/bin/env python3
"""Scan a repo's uncommitted changes for secrets with gitleaks, safely.

Run from anywhere inside the repo. Scans each added or modified tracked
file and each untracked, non-ignored file, one gitleaks call per file:
a combined stream would let one file's secret show, unredacted, as
context of another's finding, and `gitleaks dir` given several paths
scans the whole working tree instead. Skips the files the noemeo guard
treats as secrets (the same patterns, plus the repo's
.claude/noemeo-guard.json), binaries and files over the size cap, and
lists them by name. Output is always redacted.

Exit status: 0 clean, 1 leaks found, 2 couldn't scan (gitleaks missing,
not a git repo, or Python below 3.12, which the guard import needs).
"""

import os
import shutil
import subprocess
import sys
from pathlib import Path

MAX_MB = 5


def git(*args: str) -> list[str]:
    out = subprocess.run(["git", *args], capture_output=True, check=True).stdout
    return [p for p in os.fsdecode(out).split("\0") if p]


def main() -> int:
    if not shutil.which("gitleaks"):
        print("gitleaks not installed (brew install gitleaks)")
        return 2
    try:
        root = git("rev-parse", "--show-toplevel")[0].strip()
    except subprocess.CalledProcessError:
        print("not inside a git repository")
        return 2
    os.chdir(root)

    # The guard's own secret patterns, so this never scans what it blocks.
    os.environ["CLAUDE_PROJECT_DIR"] = root
    sys.path.insert(0, str(Path(__file__).resolve().parents[3] / "hooks"))
    from guard import SECRET_RE

    has_head = subprocess.run(
        ["git", "rev-parse", "--verify", "-q", "HEAD"], check=False, capture_output=True
    ).returncode == 0
    # --no-renames: a moved-and-edited file is then an add, not an R
    # the filter would drop.
    changed = (
        git("diff", "--name-only", "-z", "--no-renames", "--diff-filter=AMT", "HEAD")
        if has_head
        else []
    )
    untracked = git("ls-files", "--others", "--exclude-standard", "-z")

    skipped, leaks = [], 0
    for path in dict.fromkeys(changed + untracked):
        p = Path(path)
        if SECRET_RE.search(path):
            skipped.append(f"{path} (secret file)")
            continue
        if p.is_symlink():
            skipped.append(f"{path} (symlink)")
            continue
        if not p.is_file():
            continue
        if p.stat().st_size > MAX_MB * 1024 * 1024:
            skipped.append(f"{path} (over {MAX_MB} MB)")
            continue
        with p.open("rb") as f:
            if b"\0" in f.read(8192):
                skipped.append(f"{path} (binary)")
                continue
        result = subprocess.run(
            ["gitleaks", "dir", "-v", "--redact", "--no-banner", "--no-color",
             "--max-target-megabytes", str(MAX_MB), "--", path],
            check=False, capture_output=True, text=True,
        )
        if result.returncode == 1:
            leaks += 1
            print(result.stdout.strip() or result.stderr.strip())
        elif result.returncode != 0:
            print(f"{path}: gitleaks failed: {result.stderr.strip()}")

    for line in skipped:
        print(f"skipped: {line}")
    print(f"files with leaks: {leaks}")
    return 1 if leaks else 0


if __name__ == "__main__":
    sys.exit(main())
