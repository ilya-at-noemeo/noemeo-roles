"""skills/noemeo-worktree/scripts/noemeo-worktree: where worktrees go, what
`add` copies and installs, and when `remove` refuses or keeps a branch.

Run: python3 -m unittest discover tests

Runs the script as a subprocess against throwaway git repos (a local bare
origin, a main checkout, optional linked worktrees) in a TemporaryDirectory.
No network; poetry is a stub on PATH that records its arguments.

Dotenv file names are built in Python (ENV below) so no source line names
one literally.
"""

import os
import subprocess
import tempfile
import unittest
from pathlib import Path

SCRIPT = Path(__file__).resolve().parent.parent / "skills" / "noemeo-worktree" / "scripts" / "noemeo-worktree"
ENV = "." + "env"
ENV_LOCAL = ENV + ".local"
ENV_EXAMPLE = ENV + ".example"


def run(cwd: Path, *args: str, env=None) -> subprocess.CompletedProcess:
    return subprocess.run(list(args), cwd=cwd, capture_output=True, text=True, env=env)


class WorktreeScript(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name).resolve()
        self.env = {
            k: v for k, v in os.environ.items() if not k.startswith(("GIT_", "NOEMEO_", "POETRY_"))
        }
        self.env.update(
            HOME=str(self.tmp / "home"),
            GIT_CONFIG_GLOBAL="/dev/null",
            GIT_CONFIG_SYSTEM="/dev/null",
            GIT_AUTHOR_NAME="t",
            GIT_AUTHOR_EMAIL="t@t",
            GIT_COMMITTER_NAME="t",
            GIT_COMMITTER_EMAIL="t@t",
            NOEMEO_WORKTREES_DIR=str(self.tmp / "wt"),
        )
        (self.tmp / "home").mkdir()
        self.origin = self.tmp / "origin.git"
        self.main = self.tmp / "code" / "proj"
        self.main.mkdir(parents=True)
        self.git(self.tmp, "init", "-q", "--bare", "-b", "main", str(self.origin))
        self.git(self.main, "init", "-q", "-b", "main")
        self.git(self.main, "remote", "add", "origin", str(self.origin))
        self.commit_and_push({"README": "hi\n"})
        self.git(self.main, "remote", "set-head", "origin", "main")

    def tearDown(self) -> None:
        self._tmp.cleanup()

    def git(self, cwd: Path, *args: str) -> str:
        proc = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, env=self.env)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout.strip()

    def commit_and_push(self, files: dict) -> None:
        for name, text in files.items():
            (self.main / name).write_text(text)
            self.git(self.main, "add", name)
        self.git(self.main, "commit", "-q", "-m", "c")
        self.git(self.main, "push", "-q", "origin", "main")

    def wt(self, cwd: Path, *args: str, env=None) -> subprocess.CompletedProcess:
        return run(cwd, "bash", str(SCRIPT), *args, env=env or self.env)

    def path(self, name: str) -> Path:
        return self.tmp / "wt" / "proj" / name

    def add(self, branch: str, *extra: str) -> Path:
        proc = self.wt(self.main, "add", branch, *extra)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        return self.path(branch)

    # 1. add: location and branch

    def test_add_creates_worktree_on_new_untracked_branch_from_origin_head(self) -> None:
        self.git(self.main, "commit", "-q", "--allow-empty", "-m", "local only")  # main ahead of origin
        path = self.add("feat/x")
        self.assertEqual(path, self.tmp / "wt" / "proj" / "feat" / "x")
        self.assertEqual(self.git(path, "rev-parse", "--abbrev-ref", "HEAD"), "feat/x")
        self.assertEqual(self.git(path, "rev-parse", "HEAD"), self.git(self.main, "rev-parse", "origin/main"))
        self.assertNotEqual(self.git(path, "rev-parse", "HEAD"), self.git(self.main, "rev-parse", "HEAD"))
        upstream = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "feat/x@{upstream}"], cwd=self.main, capture_output=True, env=self.env
        )
        self.assertNotEqual(upstream.returncode, 0)

    def test_add_default_location_is_dot_worktrees_beside_main_checkout(self) -> None:
        self.env.pop("NOEMEO_WORKTREES_DIR")
        proc = self.wt(self.main, "add", "a/b")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue((self.tmp / "code" / ".worktrees" / "proj" / "a" / "b" / "README").is_file())

    def test_add_with_explicit_base(self) -> None:
        first = self.git(self.main, "rev-parse", "HEAD")
        self.commit_and_push({"two": "2\n"})
        path = self.add("old", first)
        self.assertEqual(self.git(path, "rev-parse", "HEAD"), first)

    def test_add_without_origin_head_and_base_fails(self) -> None:
        self.git(self.main, "config", "remote.origin.followRemoteHEAD", "never")  # newer git re-creates it on fetch
        self.git(self.main, "remote", "set-head", "origin", "-d")
        proc = self.wt(self.main, "add", "x")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no origin/HEAD", proc.stderr)
        self.assertFalse(self.path("x").exists())

    # 2. env files

    def test_add_copies_env_files_but_not_example(self) -> None:
        (self.main / ENV).write_text("A=1\n")
        (self.main / ENV_LOCAL).write_text("B=2\n")
        (self.main / ENV_EXAMPLE).write_text("A=\n")
        path = self.add("e")
        self.assertEqual((path / ENV).read_text(), "A=1\n")
        self.assertEqual((path / ENV_LOCAL).read_text(), "B=2\n")
        self.assertFalse((path / ENV_EXAMPLE).exists())

    # 3. existing branch, existing path

    def test_add_checks_out_existing_local_branch(self) -> None:
        self.git(self.main, "branch", "exists")
        self.git(self.main, "checkout", "-q", "exists")
        self.git(self.main, "commit", "-q", "--allow-empty", "-m", "on exists")
        tip = self.git(self.main, "rev-parse", "exists")
        self.git(self.main, "checkout", "-q", "main")
        path = self.add("exists")
        self.assertEqual(self.git(path, "rev-parse", "--abbrev-ref", "HEAD"), "exists")
        self.assertEqual(self.git(path, "rev-parse", "HEAD"), tip)

    def test_add_refuses_when_target_exists(self) -> None:
        self.path("dup").mkdir(parents=True)
        proc = self.wt(self.main, "add", "dup")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("already exists", proc.stderr)
        self.assertEqual(self.git(self.main, "branch", "--list", "dup"), "")

    # 4. from a linked worktree

    def test_add_from_inside_linked_worktree_resolves_main_checkout(self) -> None:
        first = self.add("one")
        proc = self.wt(first, "add", "two")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertTrue(self.path("two").is_dir())
        self.assertFalse((self.tmp / "wt" / "one").exists())
        self.assertIn("one", self.wt(first, "list").stdout)

    def test_add_from_linked_worktree_uses_default_location_beside_main(self) -> None:
        self.env.pop("NOEMEO_WORKTREES_DIR")
        self.assertEqual(self.wt(self.main, "add", "one").returncode, 0)
        first = self.tmp / "code" / ".worktrees" / "proj" / "one"
        self.assertEqual(self.wt(first, "add", "two").returncode, 0)
        self.assertTrue((self.tmp / "code" / ".worktrees" / "proj" / "two").is_dir())

    def test_add_branch_existing_only_on_origin_tracks_it_at_its_tip(self) -> None:
        self.git(self.main, "checkout", "-q", "-b", "pushed")
        self.git(self.main, "commit", "-q", "--allow-empty", "-m", "theirs")
        self.git(self.main, "push", "-q", "origin", "pushed")
        tip = self.git(self.main, "rev-parse", "pushed")
        self.git(self.main, "checkout", "-q", "main")
        self.git(self.main, "branch", "-q", "-D", "pushed")
        path = self.add("pushed")
        self.assertEqual(self.git(path, "rev-parse", "HEAD"), tip)
        self.assertEqual(self.git(path, "rev-parse", "--abbrev-ref", "pushed@{upstream}"), "origin/pushed")

    def test_branch_names_map_to_distinct_paths(self) -> None:
        a = self.add("a/b")
        b = self.add("a-b")
        self.assertNotEqual(a, b)
        self.assertEqual(self.git(a, "rev-parse", "--abbrev-ref", "HEAD"), "a/b")
        self.assertEqual(self.git(b, "rev-parse", "--abbrev-ref", "HEAD"), "a-b")

    # 5. remove

    def test_remove_deletes_worktree_and_merged_branch(self) -> None:
        path = self.add("m")
        proc = self.wt(self.main, "remove", "m")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(path.exists())
        self.assertEqual(self.git(self.main, "branch", "--list", "m"), "")

    def test_remove_keeps_unmerged_branch_and_mentions_force_delete(self) -> None:
        path = self.add("u")
        (path / "new").write_text("x")
        self.git(path, "add", "new")
        self.git(path, "commit", "-q", "-m", "work")
        proc = self.wt(self.main, "remove", "u")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(path.exists())
        self.assertIn("git branch -D", proc.stdout)
        self.assertEqual(self.git(self.main, "branch", "--list", "u"), "u")

    def test_remove_refuses_with_untracked_file(self) -> None:
        path = self.add("ut")
        (path / "scratch").write_text("x")
        proc = self.wt(self.main, "remove", "ut")
        self.assertNotEqual(proc.returncode, 0)
        self.assertTrue((path / "scratch").exists())
        self.assertNotEqual(self.git(self.main, "branch", "--list", "ut"), "")

    def test_remove_refuses_with_modified_file(self) -> None:
        path = self.add("mod")
        (path / "README").write_text("changed\n")
        proc = self.wt(self.main, "remove", "mod")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual((path / "README").read_text(), "changed\n")

    def test_remove_takes_back_unchanged_env_files_even_if_not_ignored(self) -> None:
        (self.main / ENV).write_text("A=1\n")
        (self.main / ENV_LOCAL).write_text("B=2\n")
        path = self.add("envok")
        self.assertTrue((path / ENV).exists())  # untracked in the worktree: would block git
        proc = self.wt(self.main, "remove", "envok")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(path.exists())
        self.assertEqual((self.main / ENV).read_text(), "A=1\n")  # main's copy untouched

    def test_remove_refuses_when_copied_env_file_was_edited(self) -> None:
        (self.main / ENV).write_text("A=1\n")
        path = self.add("envedit")
        (path / ENV).write_text("A=changed\n")
        proc = self.wt(self.main, "remove", "envedit")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual((path / ENV).read_text(), "A=changed\n")

    def test_remove_refuses_when_worktree_is_on_another_branch(self) -> None:
        path = self.add("wrong")
        self.git(path, "switch", "-q", "-c", "other")
        proc = self.wt(self.main, "remove", "wrong")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not on branch wrong", proc.stderr)
        self.assertTrue(path.exists())
        self.assertNotEqual(self.git(self.main, "branch", "--list", "other"), "")

    def test_refused_remove_puts_copied_env_files_back(self) -> None:
        (self.main / ENV).write_text("A=1\n")
        (self.main / ENV_LOCAL).write_text("B=2\n")
        path = self.add("dirty")
        (path / "scratch").write_text("x")
        proc = self.wt(self.main, "remove", "dirty")
        self.assertNotEqual(proc.returncode, 0)
        self.assertEqual((path / ENV).read_text(), "A=1\n")
        self.assertEqual((path / ENV_LOCAL).read_text(), "B=2\n")
        self.assertTrue((path / "scratch").exists())

    def test_remove_without_worktree_fails(self) -> None:
        proc = self.wt(self.main, "remove", "ghost")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("no worktree", proc.stderr)

    # 6. dependency install

    def stub_poetry(self) -> Path:
        bin_dir = self.tmp / "stubbin"
        bin_dir.mkdir()
        record = self.tmp / "poetry-call"
        stub = bin_dir / "poetry"
        stub.write_text(f'#!/bin/sh\necho "$PWD|$*|$POETRY_VIRTUALENVS_IN_PROJECT" > "{record}"\n')
        stub.chmod(0o755)
        self.env["PATH"] = f"{bin_dir}{os.pathsep}{self.env['PATH']}"
        return record

    def test_no_lockfile_no_pyproject_installs_nothing_and_stays_quiet(self) -> None:
        record = self.stub_poetry()
        proc = self.wt(self.main, "add", "plain")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertFalse(record.exists())
        self.assertNotIn("!!", proc.stdout)

    def test_pyproject_without_lockfile_warns_to_install_yourself(self) -> None:
        record = self.stub_poetry()
        self.commit_and_push({"pyproject.toml": "[project]\nname='p'\n"})
        proc = self.wt(self.main, "add", "py")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("install dependencies into .venv yourself", proc.stdout)
        self.assertFalse(record.exists())

    def test_poetry_lock_runs_poetry_install_in_the_worktree(self) -> None:
        record = self.stub_poetry()
        self.commit_and_push({"pyproject.toml": "[project]\nname='p'\n", "poetry.lock": ""})
        path = self.add("pl")
        cwd, args, in_project = record.read_text().strip().split("|")
        self.assertEqual(Path(cwd).resolve(), path)
        self.assertEqual(args, "install --quiet")
        self.assertEqual(in_project, "true")

    # 7. usage

    def test_usage_errors_exit_nonzero(self) -> None:
        for args in ([], ["bogus"], ["add"], ["remove"]):
            with self.subTest(args=args):
                proc = self.wt(self.main, *args)
                self.assertNotEqual(proc.returncode, 0)
                self.assertIn("usage", proc.stderr)

    def test_outside_a_git_repo_fails(self) -> None:
        outside = self.tmp / "nogit"
        outside.mkdir()
        proc = self.wt(outside, "list")
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("not inside a git repo", proc.stderr)

    def test_list_shows_worktrees(self) -> None:
        self.add("l")
        proc = self.wt(self.main, "list")
        self.assertEqual(proc.returncode, 0)
        self.assertIn(str(self.path("l")), proc.stdout)


if __name__ == "__main__":
    unittest.main()
