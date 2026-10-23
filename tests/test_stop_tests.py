"""The Stop hook's per-repo pytest arguments and its warning when a
checkout has tests but no .venv to run them.

Run: python3 -m unittest discover tests

Runs hooks/stop_tests.py as Claude Code does (JSON on stdin) against a
throwaway git repo whose .venv/bin/python is a stub that records its
arguments and exits with a chosen status -- no real pytest runs.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "stop_tests.py"


def git(repo: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True)


def git_out(repo: Path, *args: str) -> str:
    return subprocess.run(["git", "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout.strip()


class StopTestsHook(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.locked: list[Path] = []
        self.repo = Path(self._tmp.name).resolve() / "repo"
        self.repo.mkdir()
        git(self.repo, "init", "-q")
        git(self.repo, "-c", "user.email=t@t", "-c", "user.name=t", "commit", "-q", "--allow-empty", "-m", "init")
        (self.repo / "tests").mkdir()
        (self.repo / "tests" / "test_x.py").write_text("")
        self.args_file = self.repo / "pytest-args"

    def tearDown(self) -> None:
        for d in self.locked:
            d.chmod(0o755)
        self._tmp.cleanup()

    def linked_worktree(self, main_has_pytest: bool = True) -> Path:
        """A linked worktree of self.repo (outside it); main gets a stub pytest."""
        if main_has_pytest:
            (self.repo / ".venv" / "bin").mkdir(parents=True)
            (self.repo / ".venv" / "bin" / "pytest").write_text("")
        (self.repo / ".git" / "info" / "exclude").write_text(".venv/\npytest-args\n")
        wt = self.repo.parent / (self.repo.name + "-wt")
        git(self.repo, "worktree", "add", "-q", "--detach", str(wt))
        return wt

    def install_stub(self, exit_code: int = 0) -> None:
        bin_dir = self.repo / ".venv" / "bin"
        bin_dir.mkdir(parents=True)
        stub = bin_dir / "python"
        stub.write_text(f'#!/bin/sh\nprintf "%s\\n" "$@" > "{self.args_file}"\necho "1 failed"\nexit {exit_code}\n')
        stub.chmod(0o755)
        (bin_dir / "pytest").write_text("")
        # Keep the stub and its output out of the hook's tree hash.
        (self.repo / ".git" / "info" / "exclude").write_text(".venv/\npytest-args\n")

    def config(self, cfg) -> None:
        (self.repo / ".claude").mkdir(exist_ok=True)
        text = cfg if isinstance(cfg, str) else json.dumps(cfg)
        (self.repo / ".claude" / "noemeo-guard.json").write_text(text)

    def run_hook(self, session_id: str = "s1", project: Path | None = None) -> str:
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(project or self.repo))
        proc = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps({"session_id": session_id, "stop_hook_active": False}),
            capture_output=True,
            text=True,
            env=env,
            check=True,
        )
        return proc.stdout

    def pytest_args(self) -> list[str]:
        return self.args_file.read_text().splitlines()

    def test_repo_args_are_appended(self) -> None:
        self.install_stub()
        self.config({"stop_pytest_args": ["-m", "not browser"]})
        self.run_hook()
        self.assertEqual(self.pytest_args()[-2:], ["-m", "not browser"])

    def test_no_config_runs_plain_pytest(self) -> None:
        self.install_stub()
        self.run_hook()
        self.assertEqual(self.pytest_args()[-2:], ["-p", "no:cacheprovider"])

    def test_malformed_args_are_ignored(self) -> None:
        for bad in ('{"stop_pytest_args": "-m not browser"}', '{"stop_pytest_args": [1]}', "[]", "{not json"):
            with self.subTest(bad=bad):
                self.install_stub() if not (self.repo / ".venv").exists() else None
                self.config(bad)
                (self.repo / ".git" / "claude-tests-green").unlink(missing_ok=True)
                self.run_hook()
                self.assertEqual(self.pytest_args()[-2:], ["-p", "no:cacheprovider"])

    def test_failure_names_the_args_used(self) -> None:
        self.install_stub(exit_code=1)
        self.config({"stop_pytest_args": ["-m", "not browser"]})
        out = json.loads(self.run_hook())
        self.assertEqual(out["decision"], "block")
        self.assertIn("pytest -x -q -m 'not browser'", out["reason"])

    def test_no_venv_warns_once_per_session_in_worktree_whose_main_has_one(self) -> None:
        wt = self.linked_worktree()
        first = json.loads(self.run_hook("s1", wt))
        self.assertIn("no .venv/bin/pytest", first["systemMessage"])
        self.assertEqual(self.run_hook("s1", wt), "")
        self.assertIn("systemMessage", json.loads(self.run_hook("s2", wt)))

    def test_main_checkout_without_venv_is_silent(self) -> None:
        self.assertEqual(self.run_hook(), "")

    def test_worktree_whose_main_also_lacks_venv_is_silent(self) -> None:
        wt = self.linked_worktree(main_has_pytest=False)
        self.assertEqual(self.run_hook("s1", wt), "")

    def test_unwritable_git_dir_still_warns_and_exits_zero(self) -> None:
        wt = self.linked_worktree()
        gitdir = Path(git_out(wt, "rev-parse", "--absolute-git-dir"))
        gitdir.chmod(0o555)
        self.locked.append(gitdir)
        if os.access(gitdir, os.W_OK):
            self.skipTest("directory permissions not enforced (root?)")
        out = self.run_hook("s1", wt)  # check=True: exit 0
        self.assertIn("no .venv/bin/pytest", json.loads(out)["systemMessage"])

    def test_no_venv_and_no_tests_is_silent(self) -> None:
        (self.repo / "tests" / "test_x.py").unlink()
        (self.repo / "tests").rmdir()
        self.assertEqual(self.run_hook(), "")


if __name__ == "__main__":
    unittest.main()
