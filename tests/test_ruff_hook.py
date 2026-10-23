"""The ruff hook's warning when a repo opted in to ruff but its checkout
has no .venv/bin/ruff.

Run: python3 -m unittest discover tests

Runs hooks/ruff_touched_file.sh as Claude Code does (JSON on stdin)
against a throwaway git repo; needs jq, as the hook does.
"""

import json
import os
import subprocess
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "ruff_touched_file.sh"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


class RuffHookWithoutVenv(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.locked: list[Path] = []
        self.repo = Path(self._tmp.name).resolve() / "repo"
        self.repo.mkdir()
        subprocess.run(["git", "init", "-q", str(self.repo)], check=True)
        (self.repo / "pyproject.toml").write_text("[tool.ruff]\nline-length = 100\n")
        self.file = self.repo / "x.py"
        self.file.write_text("x = 1\n")

        git(self.repo, "add", ".")
        git(self.repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "-m", "init")

    def tearDown(self) -> None:
        for d in self.locked:
            d.chmod(0o755)
        self._tmp.cleanup()

    def linked_worktree(self, main_has_ruff: bool = True) -> Path:
        if main_has_ruff:
            ruff = self.repo / ".venv" / "bin" / "ruff"
            ruff.parent.mkdir(parents=True)
            ruff.write_text("#!/bin/sh\nexit 0\n")
            ruff.chmod(0o755)
        (self.repo / ".git" / "info" / "exclude").write_text(".venv/\n")
        wt = self.repo.parent / (self.repo.name + "-wt")
        git(self.repo, "worktree", "add", "-q", "--detach", str(wt))
        return wt

    def run_hook(self, session_id: str, file: Path | None = None) -> str:
        return self.run_hook_full(session_id, file).stdout

    def run_hook_full(self, session_id: str, file: Path | None = None) -> subprocess.CompletedProcess:
        payload = {"session_id": session_id, "tool_input": {"file_path": str(file or self.file)}}
        return subprocess.run(
            ["bash", str(HOOK)], input=json.dumps(payload), capture_output=True, text=True, check=True
        )

    def test_warns_once_per_session_in_worktree_whose_main_has_ruff(self) -> None:
        wt = self.linked_worktree()
        f = wt / "x.py"
        first = json.loads(self.run_hook("s1", f))
        self.assertIn("no .venv/bin/ruff", first["systemMessage"])
        self.assertEqual(self.run_hook("s1", f), "")
        self.assertIn("systemMessage", json.loads(self.run_hook("s2", f)))

    def test_main_checkout_without_ruff_is_silent(self) -> None:
        self.assertEqual(self.run_hook("s1"), "")

    def test_worktree_whose_main_also_lacks_ruff_is_silent(self) -> None:
        wt = self.linked_worktree(main_has_ruff=False)
        self.assertEqual(self.run_hook("s1", wt / "x.py"), "")

    def test_unwritable_git_dir_is_silent_noise_free_and_exits_zero(self) -> None:
        wt = self.linked_worktree()
        gitdir = Path(
            subprocess.run(
                ["git", "-C", str(wt), "rev-parse", "--absolute-git-dir"], capture_output=True, text=True, check=True
            ).stdout.strip()
        )
        gitdir.chmod(0o555)
        self.locked.append(gitdir)
        if os.access(gitdir, os.W_OK):
            self.skipTest("directory permissions not enforced (root?)")
        proc = self.run_hook_full("s1", wt / "x.py")  # check=True: exit 0
        self.assertEqual(proc.stderr, "")
        self.assertIn("no .venv/bin/ruff", json.loads(proc.stdout)["systemMessage"])

    def test_repo_without_ruff_table_is_silent(self) -> None:
        (self.repo / "pyproject.toml").write_text("[project]\nname = 'x'\n")
        self.assertEqual(self.run_hook("s1"), "")


if __name__ == "__main__":
    unittest.main()
