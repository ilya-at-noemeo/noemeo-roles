"""Installer manifest, exclude, drift and working-agreement regressions.

Everything runs in temp directories with a fake home; the real repos and
~/.claude, ~/.codex are never touched (the installer only reads ROOT).
"""

import importlib.util
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest
import unittest.mock
from contextlib import redirect_stdout, redirect_stderr
import io

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("install_m", ROOT / "codex" / "install.py")
installer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(installer)

GIT = ["git", "-c", "user.name=t", "-c", "user.email=t@example.com"]


def git_repo(parent, name="repo"):
    path = Path(parent) / name
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def run_main(argv, home):
    out = io.StringIO()
    with redirect_stdout(out), redirect_stderr(out):
        code = installer.main(argv, home=home)
    return code, out.getvalue()


def install_fails(argv, home):
    try:
        installer.main(argv, home=home)
    except SystemExit as exc:
        return str(exc.code)
    raise AssertionError("expected SystemExit")


def snapshot(repo):
    files = {}
    for p in sorted(Path(repo).rglob("*")):
        if ".git" in p.relative_to(repo).parts[:1] and p.relative_to(repo).parts[1:2] != ("info",):
            continue
        key = p.relative_to(repo).as_posix()
        files[key] = f"link:{os.readlink(p)}" if p.is_symlink() else (
            p.read_bytes() if p.is_file() else "dir")
    return files


def set_manifest(repo, **entries):
    mpath = repo / installer.MANIFEST
    manifest = json.loads(mpath.read_text())
    manifest.update(entries)
    mpath.write_text(json.dumps(manifest))


class ManifestTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.home = self.dir / "home"
        self.home.mkdir()
        self.repo = git_repo(self.dir)

    def install(self, *repos):
        return run_main([str(r) for r in (repos or (self.repo,))], self.home)

    def test_rerun_replaces_unchanged_stale_file(self):
        self.install()
        config = self.repo / ".codex/config.toml"
        # Simulate: an older installer wrote different text, nothing edited it since.
        config.write_text("[features]\nhooks = false\n")
        set_manifest(self.repo, **{".codex/config.toml": installer.digest(config.read_text())})
        code, _ = self.install()
        self.assertEqual(code, 0)
        self.assertEqual(config.read_text(), "[features]\nhooks = true\n")

    def test_hand_edited_file_is_conflict_and_nothing_written_in_any_repo(self):
        second = git_repo(self.dir, "second")
        self.install()  # only the first repo is installed; the second is fresh
        (self.repo / "AGENTS.md").write_text("my edits\n")
        before = snapshot(second)
        message = install_fails([str(second), str(self.repo)], self.home)
        self.assertIn("AGENTS.md", message)
        self.assertEqual(snapshot(second), before)
        self.assertEqual((self.repo / "AGENTS.md").read_text(), "my edits\n")
        self.assertFalse((second / "AGENTS.md").exists())

    def test_no_longer_planned_entry_removed_when_unchanged_conflict_when_edited(self):
        self.install()
        gone = self.repo / ".codex/agents/removed-agent.toml"
        gone.write_text("name = 'removed-agent'\n")
        set_manifest(self.repo, **{".codex/agents/removed-agent.toml": installer.digest(gone.read_text())})
        self.assertEqual(self.install()[0], 0)
        self.assertFalse(gone.exists())
        self.assertNotIn("removed-agent", (self.repo / installer.MANIFEST).read_text())
        # Edited since: conflict, file preserved.
        gone.write_text("name = 'removed-agent'\n")
        set_manifest(self.repo, **{".codex/agents/removed-agent.toml": "sha256:original"})
        message = install_fails([str(self.repo)], self.home)
        self.assertIn("no longer generated, but edited since", message)
        self.assertTrue(gone.exists())

    def test_repo_local_skills_linked_including_symlinked_dir(self):
        local = self.repo / ".claude/skills/local-one"
        local.mkdir(parents=True)
        (local / "SKILL.md").write_text("---\nname: local-one\n---\n")
        elsewhere = self.dir / "shared/linked-src"
        elsewhere.mkdir(parents=True)
        (elsewhere / "SKILL.md").write_text("---\nname: linked\n---\n")
        (self.repo / ".claude/skills/linked").symlink_to(elsewhere, target_is_directory=True)
        self.install()
        skills = self.repo / ".agents/skills"
        self.assertEqual((skills / "local-one").resolve(), local.resolve())
        self.assertEqual((skills / "linked").resolve(), elsewhere.resolve())
        self.assertEqual((skills / "noemeo-ship").resolve(), (ROOT / "skills/noemeo-ship").resolve())

    def test_skill_name_collision_conflicts_unless_same_source(self):
        clash = self.repo / ".claude/skills/noemeo-ship"
        clash.mkdir(parents=True)
        (clash / "SKILL.md").write_text("---\nname: noemeo-ship\n---\n")
        message = install_fails([str(self.repo)], self.home)
        self.assertIn("skill 'noemeo-ship' comes from both", message)
        self.assertFalse((self.repo / "AGENTS.md").exists())
        shutil.rmtree(clash)
        clash.symlink_to(ROOT / "skills/noemeo-ship", target_is_directory=True)
        self.assertEqual(self.install()[0], 0)

    def test_old_agents_skills_symlink_reported_once_and_blocks(self):
        (self.repo / ".agents").mkdir()
        (self.repo / ".agents/skills").symlink_to(ROOT / "skills", target_is_directory=True)
        message = install_fails([str(self.repo)], self.home)
        self.assertEqual(message.count("in the way"), 1)
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertFalse((self.repo / installer.MANIFEST).exists())

    def generated(self, repo):
        manifest = json.loads((repo / installer.MANIFEST).read_text())
        return sorted(manifest) + [installer.MANIFEST.as_posix()]

    def test_exclude_block_lists_everything_replaced_not_duplicated_keeps_others(self):
        exclude = self.repo / ".git/info/exclude"
        exclude.parent.mkdir(exist_ok=True)
        exclude.write_text("*.log\nmy-private-dir/\n")
        self.install()
        self.install()
        text = exclude.read_text()
        self.assertEqual(text.count(installer.BEGIN), 1)
        self.assertEqual(text.count(installer.END), 1)
        self.assertIn("*.log\nmy-private-dir/\n", text)
        lines = text.splitlines()
        for rel in self.generated(self.repo):
            self.assertIn("/" + rel, lines)
        self.assertIn("/.codex/noemeo-install.json", lines)
        status = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                                capture_output=True, text=True, check=True).stdout
        self.assertEqual(status, "")

    def test_exclude_in_linked_worktree_lands_in_common_git_dir(self):
        subprocess.run([*GIT, "-C", str(self.repo), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
        tree = self.dir / "wt"
        subprocess.run(["git", "-C", str(self.repo), "worktree", "add", "-q", str(tree), "-b", "b"], check=True)
        self.install(tree)
        common = self.repo / ".git/info/exclude"
        self.assertIn(installer.BEGIN, common.read_text())
        self.assertIn("/AGENTS.md", common.read_text())
        status = subprocess.run(["git", "-C", str(tree), "status", "--porcelain"],
                                capture_output=True, text=True, check=True).stdout
        self.assertEqual(status, "")

    def test_check_reports_problems_writes_nothing_and_passes_when_current(self):
        self.install()
        self.assertEqual(run_main(["--check", str(self.repo)], self.home)[0], 0)
        cases = {
            "missing": lambda: (self.repo / ".codex/hooks.json").unlink(),
            "edited": lambda: (self.repo / "AGENTS.md").write_text("edited\n"),
            "stale": lambda: (
                (self.repo / ".codex/config.toml").write_text("old\n"),
                set_manifest(self.repo, **{".codex/config.toml": installer.digest("old\n")})),
        }
        for label, damage in cases.items():
            with self.subTest(label):
                self.tearDownRepo()
                self.install()
                damage()
                before = snapshot(self.repo)
                code, out = run_main(["--check", str(self.repo)], self.home)
                self.assertEqual(code, 1, out)
                self.assertEqual(snapshot(self.repo), before)

    def tearDownRepo(self):
        for rel in ("AGENTS.md", ".codex", ".agents"):
            p = self.repo / rel
            if p.is_dir():
                shutil.rmtree(p)
            elif p.exists():
                p.unlink()


class InstallerHardeningTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name).resolve()
        self.home = self.dir / "home"
        self.home.mkdir()
        self.repo = git_repo(self.dir)
        self.outside = self.dir / "outside"
        self.outside.mkdir()

    def install(self, *repos):
        return run_main([str(r) for r in (repos or (self.repo,))], self.home)

    def test_worktrees_sharing_exclude_keep_their_own_blocks(self):
        local = self.repo / ".claude/skills/localskill"
        local.mkdir(parents=True)
        (local / "SKILL.md").write_text("---\nname: localskill\n---\n")
        subprocess.run([*GIT, "-C", str(self.repo), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
        tree = self.dir / "wt"
        subprocess.run(["git", "-C", str(self.repo), "worktree", "add", "-q", str(tree), "-b", "b"], check=True)
        self.install()
        self.install(tree)
        self.install(self.repo, tree)
        text = (self.repo / ".git/info/exclude").read_text()
        self.assertEqual(text.count(f"{installer.BEGIN} {self.repo}\n"), 1)
        self.assertEqual(text.count(f"{installer.BEGIN} {tree}\n"), 1)
        self.assertIn("/.agents/skills/localskill", text)
        status = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                                capture_output=True, text=True, check=True).stdout
        for generated in ("AGENTS.md", ".codex", ".agents"):
            self.assertNotIn(generated, status)

    def test_manifest_keys_outside_checkout_conflict_and_files_survive(self):
        self.install()
        victim = self.outside / "victim.txt"
        victim.write_text("keep me\n")
        for key in (str(victim), "../outside/victim.txt"):
            with self.subTest(key=key):
                set_manifest(self.repo, **{key: installer.digest("keep me\n")})
                message = install_fails([str(self.repo)], self.home)
                self.assertIn("outside the checkout", message)
                self.assertEqual(victim.read_text(), "keep me\n")
                (self.repo / installer.MANIFEST).unlink()
                self.install()

    def test_bad_manifest_is_conflict_and_outside_file_untouched(self):
        target = self.outside / "target.json"
        target.write_text("{}")
        (self.repo / ".codex").mkdir()
        manifest = self.repo / installer.MANIFEST
        manifest.symlink_to(target)
        self.assertIn("not a manifest", install_fails([str(self.repo)], self.home))
        self.assertEqual(target.read_text(), "{}")
        manifest.unlink()
        for text in ("not json", "[1, 2]", '{"AGENTS.md": 5}'):
            with self.subTest(text=text):
                manifest.write_text(text)
                self.assertIn("not a manifest", install_fails([str(self.repo)], self.home))
                self.assertEqual(manifest.read_text(), text)
                self.assertFalse((self.repo / "AGENTS.md").exists())

    def test_begin_without_end_is_conflict_before_any_write(self):
        exclude = self.repo / ".git/info/exclude"
        exclude.parent.mkdir(exist_ok=True)
        exclude.write_text(f"keep\n{installer.BEGIN} {self.repo}\n/AGENTS.md\n")
        self.assertIn("fix it by hand", install_fails([str(self.repo)], self.home))
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertFalse((self.repo / ".codex").exists())

    def test_end_before_begin_is_harmless(self):
        exclude = self.repo / ".git/info/exclude"
        exclude.parent.mkdir(exist_ok=True)
        exclude.write_text(f"{installer.END}\nkeep\n")
        self.assertEqual(self.install()[0], 0)
        text = exclude.read_text()
        self.assertIn("keep\n", text)
        self.assertIn(f"{installer.BEGIN} {self.repo}", text)

    def test_unwritable_exclude_is_conflict_before_any_write(self):
        exclude = self.repo / ".git/info/exclude"
        exclude.parent.mkdir(exist_ok=True)
        exclude.write_text("keep\n")
        exclude.chmod(0o444)
        self.addCleanup(exclude.chmod, 0o644)
        if os.access(exclude, os.W_OK):
            self.skipTest("running with privileges that ignore file modes")
        self.assertIn("not writable", install_fails([str(self.repo)], self.home))
        self.assertFalse((self.repo / "AGENTS.md").exists())
        self.assertEqual(exclude.read_text(), "keep\n")

    def test_identical_preexisting_file_is_not_adopted(self):
        config = self.repo / ".codex/config.toml"
        config.parent.mkdir()
        config.write_text("[features]\nhooks = true\n")
        self.install()
        manifest = json.loads((self.repo / installer.MANIFEST).read_text())
        self.assertNotIn(".codex/config.toml", manifest)
        self.assertIn(".codex/hooks.json", manifest)
        self.assertNotIn("/.codex/config.toml", (self.repo / ".git/info/exclude").read_text())
        self.assertEqual(self.install()[0], 0)
        self.assertNotIn(".codex/config.toml", json.loads((self.repo / installer.MANIFEST).read_text()))

    def test_removal_through_symlinked_parent_is_conflict(self):
        self.install()
        victim = self.outside / "victim.txt"
        victim.write_text("keep me\n")
        (self.repo / "linked").symlink_to(self.outside, target_is_directory=True)
        set_manifest(self.repo, **{"linked/victim.txt": installer.digest("keep me\n")})
        message = install_fails([str(self.repo)], self.home)
        self.assertIn("in the way of", message)
        self.assertEqual(victim.read_text(), "keep me\n")

    def worktree_pair(self):
        local = self.repo / ".claude/skills/localskill"
        local.mkdir(parents=True)
        (local / "SKILL.md").write_text("---\nname: localskill\n---\n")
        subprocess.run([*GIT, "-C", str(self.repo), "commit", "-q", "--allow-empty", "-m", "x"], check=True)
        tree = self.dir / "wt"
        subprocess.run(["git", "-C", str(self.repo), "worktree", "add", "-q", str(tree), "-b", "b"], check=True)
        return tree

    def test_main_and_worktree_in_one_run_keep_both_blocks(self):
        tree = self.worktree_pair()
        self.assertEqual(self.install(self.repo, tree)[0], 0)
        text = (self.repo / ".git/info/exclude").read_text()
        self.assertEqual(text.count(f"{installer.BEGIN} {self.repo}\n"), 1)
        self.assertEqual(text.count(f"{installer.BEGIN} {tree}\n"), 1)
        status = subprocess.run(["git", "-C", str(self.repo), "status", "--porcelain"],
                                capture_output=True, text=True, check=True).stdout
        for generated in ("AGENTS.md", ".codex", ".agents"):
            self.assertNotIn(generated, status)

    def test_tracked_manifest_is_conflict(self):
        self.install()
        subprocess.run(["git", "-C", str(self.repo), "add", "-f", str(installer.MANIFEST)], check=True)
        self.assertIn("tracked by Git", install_fails([str(self.repo)], self.home))

    def test_tracked_file_named_in_manifest_is_never_removed(self):
        self.install()
        mine = self.repo / "tracked.txt"
        mine.write_text("committed\n")
        subprocess.run(["git", "-C", str(self.repo), "add", "tracked.txt"], check=True)
        set_manifest(self.repo, **{"tracked.txt": installer.digest("committed\n")})
        self.assertIn("tracked by Git", install_fails([str(self.repo)], self.home))
        self.assertEqual(mine.read_text(), "committed\n")

    def test_check_flags_missing_or_outdated_exclude_block(self):
        self.install()
        self.assertEqual(run_main(["--check", str(self.repo)], self.home)[0], 0)
        exclude = self.repo / ".git/info/exclude"
        good = exclude.read_text()
        for label, text in (("emptied", ""), ("outdated", good.replace("/AGENTS.md\n", ""))):
            with self.subTest(label):
                exclude.write_text(text)
                code, out = run_main(["--check", str(self.repo)], self.home)
                self.assertEqual(code, 1, out)
                self.assertEqual(exclude.read_text(), text)

    def test_old_marker_block_is_replaced_by_one_new_block(self):
        exclude = self.repo / ".git/info/exclude"
        exclude.parent.mkdir(exist_ok=True)
        exclude.write_text(f"before\n{installer.OLD_BEGIN}\n/AGENTS.md\n/.codex/config.toml\n"
                           f"{installer.END}\nafter\n")
        self.install()
        text = exclude.read_text()
        self.assertNotIn(installer.OLD_BEGIN, text)
        self.assertEqual(text.count(f"{installer.BEGIN} {self.repo}\n"), 1)
        self.assertEqual(text.count(installer.END), 1)
        self.assertIn("before\n", text)
        self.assertIn("after\n", text)


adapter_spec = importlib.util.spec_from_file_location("hook_adapter_m", ROOT / "codex" / "hook_adapter.py")
adapter = importlib.util.module_from_spec(adapter_spec)
adapter_spec.loader.exec_module(adapter)


class AdapterProjectDirTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.repo = git_repo(Path(self.tmp.name).resolve())
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/noemeo-guard.json").write_text(json.dumps(
            {"secrets": ["local.token"], "aws_profiles": ["noemeo-dev"]}))
        (self.repo / "src").mkdir()
        env = {k: v for k, v in os.environ.items() if k != "AWS_PROFILE"}
        patcher = unittest.mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def bash(self, command, cwd):
        return adapter.dispatch({"hook_event_name": "PreToolUse", "cwd": str(cwd),
                                 "tool_name": "Bash", "tool_input": {"command": command}})

    def test_policy_applies_from_a_subdirectory(self):
        for cwd in (self.repo, self.repo / "src"):
            with self.subTest(cwd=cwd.name):
                self.assertTrue(adapter.denied(self.bash("aws s3 ls", cwd)))
                self.assertTrue(adapter.denied(self.bash("cat ../local.token" if cwd.name == "src"
                                                          else "cat local.token", cwd)))
        self.assertFalse(adapter.denied(self.bash("aws s3 ls --profile noemeo-dev", self.repo / "src")))

    def test_raw_exec_workdir_subdirectory_uses_repo_policy(self):
        result = adapter.dispatch({"hook_event_name": "PreToolUse", "cwd": self.tmp.name,
            "tool_name": "exec_command", "tool_input": {
            "cmd": "aws s3 ls", "workdir": str(self.repo / "src")}})
        self.assertTrue(adapter.denied(result))

    def test_project_dir_is_toplevel_in_git_and_cwd_outside(self):
        self.assertEqual(adapter.project_dir(self.repo / "src"), str(self.repo))
        with tempfile.TemporaryDirectory() as plain:
            plain = str(Path(plain).resolve())
            with unittest.mock.patch.dict(os.environ, {"GIT_CEILING_DIRECTORIES": str(Path(plain).parent)}):
                self.assertEqual(adapter.project_dir(plain), plain)


class AdapterSessionPolicyTest(unittest.TestCase):
    """The session's repo policy binds commands run from any workdir."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name).resolve()
        self.repo = git_repo(self.dir)
        (self.repo / ".claude").mkdir()
        (self.repo / ".claude/noemeo-guard.json").write_text(json.dumps(
            {"secrets": ["local.token"], "aws_profiles": ["acme-dev"]}))
        self.elsewhere = self.dir / "elsewhere"
        self.elsewhere.mkdir()
        env = {k: v for k, v in os.environ.items() if k != "AWS_PROFILE"}
        env["GIT_CEILING_DIRECTORIES"] = str(self.dir)
        patcher = unittest.mock.patch.dict(os.environ, env, clear=True)
        patcher.start()
        self.addCleanup(patcher.stop)

    def exec(self, session, command, workdir=None):
        data = {"cmd": command}
        if workdir:
            data["workdir"] = str(workdir)
        return adapter.dispatch({"hook_event_name": "PreToolUse", "cwd": str(session),
                                 "tool_name": "exec_command", "tool_input": data})

    def test_a_workdir_outside_the_repo(self):
        self.assertTrue(adapter.denied(self.exec(self.repo, "aws s3 ls", self.elsewhere)))
        self.assertFalse(adapter.denied(
            self.exec(self.repo, "aws s3 ls --profile acme-dev", self.elsewhere)))

    def test_b_nested_repo_without_policy(self):
        nested = self.repo / "vendor/lib"
        nested.mkdir(parents=True)
        subprocess.run(["git", "init", "-q", str(nested)], check=True)
        self.assertTrue(adapter.denied(self.exec(self.repo, "aws s3 ls", nested)))

    def test_c_secret_read_from_outside_workdir(self):
        self.assertTrue(adapter.denied(
            self.exec(self.repo, f"cat {self.repo}/local.token", self.elsewhere)))

    def test_d_apply_patch_on_secret(self):
        result = adapter.dispatch({"hook_event_name": "PreToolUse", "cwd": str(self.repo),
            "tool_name": "apply_patch", "tool_input": {"command":
            "*** Begin Patch\n*** Update File: local.token\n*** End Patch"}})
        self.assertTrue(adapter.denied(result))

    def test_e_non_git_session_with_workdir_repo_policy(self):
        plain = self.dir / "plain"
        plain.mkdir()
        self.assertTrue(adapter.denied(self.exec(plain, "cat local.token", self.repo)))


class CopyDriftTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.home = self.dir / "home"
        (self.home / ".claude/plugins").mkdir(parents=True)
        self.repo = git_repo(self.dir)

    def register(self, market_path, copy):
        (self.home / ".claude/plugins/known_marketplaces.json").write_text(
            json.dumps({"mk": {"source": {"path": str(market_path)}}}))
        (self.home / ".claude/plugins/installed_plugins.json").write_text(
            json.dumps({"plugins": {"noemeo@mk": [{"installPath": str(copy), "version": "1"}]}}))

    def make_copy(self):
        copy = self.dir / "installed"
        for part in installer.PLUGIN_DIRS:
            shutil.copytree(ROOT / part, copy / part, symlinks=True,
                            ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
        return copy

    def test_claude_copy_identical_ok_one_differing_file_is_problem(self):
        copy = self.make_copy()
        self.register(ROOT, copy)
        (copy / "hooks/__pycache__").mkdir(exist_ok=True)
        (copy / "hooks/__pycache__/x.pyc").write_bytes(b"junk")
        (copy / "roles/.DS_Store").write_bytes(b"junk")
        self.assertEqual(installer.copy_drift(ROOT, [self.repo], self.home), [])
        target = copy / "roles/working-agreement.md"
        target.write_text(target.read_text() + "\nextra\n")
        problems = installer.copy_drift(ROOT, [self.repo], self.home)
        self.assertEqual(len(problems), 1)
        self.assertIn("roles/working-agreement.md", problems[0])

    def test_marketplace_for_another_directory_is_ignored(self):
        copy = self.make_copy()
        (copy / "agents/noemeo-code-reviewer.md").write_text("different\n")
        other = self.dir / "other-marketplace"
        other.mkdir()
        self.register(other, copy)
        self.assertEqual(installer.copy_drift(ROOT, [self.repo], self.home), [])

    def test_codex_cached_skill_differing_from_linked_source_is_problem(self):
        cached = self.home / ".codex/plugins/cache/m/noemeo/1/skills/noemeo-ship"
        shutil.copytree(ROOT / "skills/noemeo-ship", cached,
                        ignore=shutil.ignore_patterns("__pycache__", ".DS_Store"))
        self.assertEqual(installer.copy_drift(ROOT, [self.repo], self.home), [])
        (cached / "SKILL.md").write_text("changed\n")
        problems = installer.copy_drift(ROOT, [self.repo], self.home)
        self.assertEqual(len(problems), 1)
        self.assertIn(str(cached), problems[0])

    def test_same_named_skill_of_another_plugin_is_ignored(self):
        other = self.home / ".codex/plugins/cache/m/unrelated/1/skills/noemeo-ship"
        other.mkdir(parents=True)
        (other / "SKILL.md").write_text("a different plugin's skill\n")
        self.assertEqual(installer.copy_drift(ROOT, [self.repo], self.home), [])

    def write_registry(self, markets, plugins):
        (self.home / ".claude/plugins/known_marketplaces.json").write_text(json.dumps(markets))
        (self.home / ".claude/plugins/installed_plugins.json").write_text(json.dumps({"plugins": plugins}))

    def test_github_marketplace_without_path_does_not_hide_stale_copy(self):
        copy = self.make_copy()
        (copy / "agents/noemeo-code-reviewer.md").write_text("different\n")
        self.write_registry(
            {"gh": {"source": {"source": "github", "repo": "x/y"}},
             "mk": {"source": {"path": str(ROOT)}}},
            {"noemeo@mk": [{"installPath": str(copy), "version": "1"}]})
        problems = installer.copy_drift(ROOT, [self.repo], self.home)
        self.assertEqual(len(problems), 1)
        self.assertIn("noemeo@mk", problems[0])

    def test_malformed_entries_do_not_crash_or_hide_other_results(self):
        copy = self.make_copy()
        (copy / "agents/noemeo-code-reviewer.md").write_text("different\n")
        self.write_registry(
            {"bad": "not a dict", "worse": {"source": "str"}, "mk": {"source": {"path": str(ROOT)}}},
            {"noemeo@mk": [{"version": "1"}, "junk", {"installPath": str(copy), "version": "2"}],
             "x@bad": "junk"})
        problems = installer.copy_drift(ROOT, [self.repo], self.home)
        self.assertTrue(any("(2) differs" in p for p in problems), problems)
        self.assertTrue(any("without an install path" in p for p in problems), problems)


class SessionContextTest(unittest.TestCase):
    def run_script(self, project, cwd):
        script = os.path.relpath(ROOT / "hooks/session_context.sh", os.path.realpath(cwd))
        env = {"PATH": "/usr/bin:/bin", "CLAUDE_PROJECT_DIR": str(project),
               "GIT_CEILING_DIRECTORIES": str(Path(project).parent), "HOME": str(cwd)}
        return subprocess.run(["bash", script], cwd=cwd, env=env, capture_output=True,
                              text=True, timeout=60)

    def test_prints_agreement_from_other_repo_and_relative_invocation(self):
        with tempfile.TemporaryDirectory() as tmp:
            repo = git_repo(tmp)
            elsewhere = Path(tmp) / "elsewhere"
            elsewhere.mkdir()
            out = self.run_script(repo, elsewhere).stdout
            self.assertIn("## Noemeo working agreement", out)
            self.assertIn("Repo state at session start", out)

    def test_prints_nothing_outside_a_git_repo(self):
        with tempfile.TemporaryDirectory() as tmp:
            plain = Path(tmp) / "plain"
            plain.mkdir()
            result = self.run_script(plain, plain)
            self.assertEqual(result.stdout, "")


class RoleDocsTest(unittest.TestCase):
    def test_codex_agents_role_list_matches_role_files(self):
        text = (ROOT / "codex/AGENTS.md").read_text()
        listed = set(re.findall(r"`(roles/[a-z-]+/[a-z-]+\.md)`", text))
        actual = {p.relative_to(ROOT).as_posix() for p in (ROOT / "roles").glob("*/*.md")}
        self.assertEqual(listed, actual)
        for rel in listed:
            self.assertTrue((ROOT / rel).is_file(), rel)
        self.assertIn("roles/working-agreement.md", text)
        self.assertTrue((ROOT / "roles/working-agreement.md").is_file())

    def test_every_agent_references_working_agreement(self):
        agents = sorted((ROOT / "agents").glob("*.md"))
        self.assertTrue(agents)
        for agent in agents:
            self.assertIn("working-agreement.md", agent.read_text(), agent.name)

    def test_aws_default_credentials_rule_lives_only_in_working_agreement(self):
        phrase = "never the default credentials"
        places = [*(ROOT / "agents").rglob("*.md"), *(ROOT / "roles").rglob("*.md"),
                  *(ROOT / "codex").rglob("*.md"), *(ROOT / "skills/noemeo-ship").rglob("*.md")]
        found = {p.relative_to(ROOT).as_posix() for p in places
                 if phrase in " ".join(p.read_text().lower().split())}
        self.assertEqual(found, {"roles/working-agreement.md"})


if __name__ == "__main__":
    unittest.main()
