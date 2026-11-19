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


class HookCase(unittest.TestCase):
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



class StopTestsHook(HookCase):
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


def decision(repo: Path, rel: str, id: str, **fields: str) -> None:
    """A decision record under `repo`; extra fields are raw `key: value` text."""
    values = {"id": id, "kind": "policy", "status": "accepted", "binding": "true",
              "summary": f"Summary of {id}", **fields}
    front = "\n".join(f"{k}: {v}" for k, v in values.items())
    path = repo / rel
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(f"---\n{front}\n---\n# Record {id}\n\n## How to apply\nDo {id}.\n")


class StopLint(HookCase):
    """Decision lint runs from the Stop hook when the repo has decision_roots."""

    def with_duplicate_ids(self) -> None:
        self.config({"decision_roots": ["docs/decisions"]})
        decision(self.repo, "docs/decisions/a.md", "acme-dup")
        decision(self.repo, "docs/decisions/b.md", "acme-dup")

    def with_only_warnings(self) -> None:
        self.config({"decision_roots": ["docs/decisions"]})
        decision(self.repo, "docs/decisions/ok.md", "acme-ok")
        decision(self.repo, "docs/decisions/nosum.md", "acme-nosum", summary='""')

    def test_lint_error_blocks_the_stop(self) -> None:
        self.with_duplicate_ids()  # no .venv at all: lint needs only the standard library
        out = json.loads(self.run_hook())
        self.assertEqual(out["decision"], "block")
        self.assertIn("error:", out["reason"])
        self.assertIn("acme-dup", out["reason"])

    def test_lint_error_blocks_even_when_the_tests_pass(self) -> None:
        self.install_stub(exit_code=0)
        self.with_duplicate_ids()
        out = json.loads(self.run_hook())
        self.assertEqual(out["decision"], "block")
        self.assertIn("acme-dup", out["reason"])

    def test_lint_warnings_do_not_block(self) -> None:
        self.with_only_warnings()
        out = self.run_hook()  # no .venv
        self.assertNotEqual(json.loads(out).get("decision") if out else None, "block")
        self.install_stub(exit_code=0)
        (self.repo / ".git" / "claude-tests-green").unlink(missing_ok=True)
        out = self.run_hook()
        self.assertNotEqual(json.loads(out).get("decision") if out else None, "block")

    def test_clean_decisions_do_not_change_the_stop(self) -> None:
        self.config({"decision_roots": ["docs/decisions"]})
        decision(self.repo, "docs/decisions/ok.md", "acme-ok")
        self.assertEqual(self.run_hook(), "")

    def test_no_decision_roots_means_no_lint(self) -> None:
        decision(self.repo, "docs/decisions/a.md", "acme-dup")
        decision(self.repo, "docs/decisions/b.md", "acme-dup")
        self.assertEqual(self.run_hook(), "")  # no config at all
        self.config({"stop_pytest_args": []})
        self.assertEqual(self.run_hook(), "")  # config without decision_roots

    def test_failing_tests_still_block_when_lint_is_clean(self) -> None:
        self.install_stub(exit_code=1)
        self.config({"decision_roots": ["docs/decisions"]})
        decision(self.repo, "docs/decisions/ok.md", "acme-ok")
        out = json.loads(self.run_hook())
        self.assertEqual(out["decision"], "block")
        self.assertIn("Tests are failing", out["reason"])

    def test_an_internal_lint_failure_does_not_block_and_is_named_on_stderr(self) -> None:
        # a copy of the hooks whose decisions module fails inside load()/lint_corpus()
        hooks = self.repo.parent / "hooks-broken"
        hooks.mkdir()
        for name in ("stop_tests.py", "decisions_format.py"):
            (hooks / name).write_text((HOOK.parent / name).read_text())
        (hooks / "decisions.py").write_text(
            "class Corpus:\n    pass\n\n"
            "def load(project):\n    raise RuntimeError('boom')\n\n"
            "def lint_corpus(corpus, project):\n    raise RuntimeError('boom')\n"
        )
        self.install_stub(exit_code=0)
        self.with_duplicate_ids()
        proc = subprocess.run(
            [sys.executable, str(hooks / "stop_tests.py")],
            input=json.dumps({"session_id": "s1", "stop_hook_active": False}),
            capture_output=True,
            text=True,
            env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.repo)),
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        if proc.stdout.strip():
            self.assertNotEqual(json.loads(proc.stdout).get("decision"), "block")
        lines = [ln for ln in proc.stderr.splitlines() if ln.strip()]
        self.assertEqual(len(lines), 1, proc.stderr)
        self.assertIn("decisions", lines[0])
        self.assertIn("lint", lines[0])


if __name__ == "__main__":
    unittest.main()
