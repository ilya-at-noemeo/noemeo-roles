"""What a code review covered: a fingerprint of a repo's changes against
its base branch, and the record of reviews per fingerprint.

The fingerprint hashes the content of every file that differs from the
merge-base with the base branch -- committed, uncommitted or untracked
(not ignored) alike -- so committing reviewed changes keeps it, and any
further edit changes it. Records live in the repo's git directory
(`noemeo-reviews.jsonl`), never in the tree. Shared by review_record.py
(SubagentStop) and review_gate.py (PreToolUse).
"""

import hashlib
import json
import subprocess
import time
from pathlib import Path

RECORDS = "noemeo-reviews.jsonl"


def git(repo: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(repo), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def toplevel(path: Path) -> Path | None:
    try:
        return Path(git(path, "rev-parse", "--show-toplevel"))
    except (subprocess.CalledProcessError, FileNotFoundError, NotADirectoryError):
        return None


def candidate_bases(repo: Path) -> list[str]:
    """The base a PR from this repo would most likely target: the remote's
    default branch, plus `dev` where it exists (infra repos work on dev)."""
    bases = []
    try:
        bases.append(git(repo, "symbolic-ref", "--short", "refs/remotes/origin/HEAD"))
    except subprocess.CalledProcessError:
        pass
    for name in ("origin/dev", "origin/main"):
        try:
            git(repo, "rev-parse", "--verify", "--quiet", name)
            bases.append(name)
        except subprocess.CalledProcessError:
            pass
    return list(dict.fromkeys(bases))


def fingerprint(repo: Path, base: str) -> str | None:
    """Hash of the changed files' content relative to merge-base(base, HEAD);
    None when the base can't be resolved."""
    try:
        mb = git(repo, "merge-base", base, "HEAD")
    except subprocess.CalledProcessError:
        return None
    changed = set(git(repo, "diff", "--name-only", mb).splitlines())
    changed |= set(git(repo, "ls-files", "--others", "--exclude-standard").splitlines())
    h = hashlib.sha256(mb.encode())
    for rel in sorted(p for p in changed if p and "__pycache__" not in p):
        f = repo / rel
        digest = hashlib.sha256(f.read_bytes()).hexdigest() if f.is_file() else "deleted"
        h.update(f"\0{rel}\0{digest}".encode())
    return h.hexdigest()


def records_path(repo: Path) -> Path:
    return (repo / git(repo, "rev-parse", "--git-common-dir")).resolve() / RECORDS


def record(repo: Path, verdict: str, summary: str) -> list[str]:
    """Record a review of the repo's current state against each candidate
    base; returns the bases recorded."""
    done = []
    with open(records_path(repo), "a") as out:
        for base in candidate_bases(repo):
            fp = fingerprint(repo, base)
            if fp:
                row = {"time": time.time(), "base": base, "fingerprint": fp, "verdict": verdict}
                out.write(json.dumps({**row, "summary": summary[:500]}) + "\n")
                done.append(base)
    return done


def latest(repo: Path, base: str) -> dict | None:
    """The most recent review whose fingerprint matches the current state."""
    fp = fingerprint(repo, base)
    path = records_path(repo)
    if not fp or not path.exists():
        return None
    match = None
    for line in path.read_text().splitlines():
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if row.get("fingerprint") == fp:
            match = row
    return match
