"""Which bases a review is recorded against, and that the gate then
lets a PR through for each -- including a PR stacked on another branch.

Run: python3 -m unittest discover tests

Builds a throwaway origin and clone: `main`, a branch already merged into
it (`old`), an open branch `a`, and `b` stacked on `a`.
"""

import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HOOKS))
from review_state import latest, record  # noqa: E402

G = "gh pr " + "create"  # split so this file's own text never trips a gate


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def commit(repo: Path, name: str) -> None:
    (repo / name).write_text(name)
    git(repo, "add", name)
    git(repo, "commit", "-q", "-m", name)


class StackedBases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        origin = root / "origin.git"
        git(root, "init", "-q", "--bare", "-b", "main", str(origin))
        self.repo = root / "work"
        git(root, "clone", "-q", str(origin), str(self.repo))
        for key, value in (("user.name", "t"), ("user.email", "t@example.com")):
            git(self.repo, "config", key, value)
        git(self.repo, "checkout", "-q", "-b", "main")
        commit(self.repo, "base")
        git(self.repo, "push", "-q", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        # `old`: pushed, then merged into main.
        git(self.repo, "checkout", "-q", "-b", "old")
        commit(self.repo, "old")
        git(self.repo, "push", "-q", "origin", "old")
        git(self.repo, "checkout", "-q", "main")
        git(self.repo, "merge", "-q", "--ff-only", "old")
        git(self.repo, "push", "-q", "origin", "main")
        # `a`: open; `b`: stacked on it.
        git(self.repo, "checkout", "-q", "-b", "a")
        commit(self.repo, "a")
        git(self.repo, "push", "-q", "origin", "a")
        git(self.repo, "checkout", "-q", "-b", "b")
        commit(self.repo, "b")
        git(self.repo, "push", "-q", "origin", "b")

    def tearDown(self):
        self.tmp.cleanup()

    def gate(self, base: str) -> str:
        event = {
            "tool_name": "Bash",
            "tool_input": {"command": f"{G} --base {base} --fill"},
            "cwd": str(self.repo),
        }
        return subprocess.run(
            [sys.executable, str(HOOKS / "review_gate.py")],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            check=True,
        ).stdout

    def test_records_the_default_base_and_the_branch_it_is_stacked_on(self):
        self.assertEqual(record(self.repo, "Ready", "ok"), ["origin/main", "origin/a"])

    def test_a_stacked_pr_passes_the_gate_once_reviewed(self):
        self.assertIn("deny", self.gate("a"))
        record(self.repo, "Ready with nits", "ok")
        self.assertEqual(self.gate("a"), "")
        self.assertEqual(self.gate("main"), "")

    def test_an_edit_after_the_review_voids_it_for_the_stacked_base(self):
        record(self.repo, "Ready", "ok")
        (self.repo / "b").write_text("changed")
        self.assertIsNone(latest(self.repo, "origin/a"))
        self.assertIn("deny", self.gate("a"))

    def test_merged_and_own_branches_are_not_recorded(self):
        bases = record(self.repo, "Ready", "ok")
        self.assertNotIn("origin/old", bases)
        self.assertNotIn("origin/b", bases)


if __name__ == "__main__":
    unittest.main()
