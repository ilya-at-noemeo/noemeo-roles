"""`version_of`: a decision's version is the Git commit that introduced its
current committed content; `drift` says the working tree differs from it.

Run: /opt/homebrew/bin/python3.13 -m pytest tests/test_decisions_version.py

Every repo is a throwaway `git init` in a temp directory; names are
invented (`acme`). No network.
"""

import dataclasses
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HOOKS))
import decisions  # noqa: E402
from decisions import load  # noqa: E402


def version_of(d):
    return decisions.version_of(d)  # looked up at call time: one failure per test


def Version(commit, drift):  # noqa: N802
    return decisions.Version(commit, drift)


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True, capture_output=True, text=True,
    ).stdout.strip()


def record(id, body="Do it."):
    return (
        f"---\nid: {id}\nkind: policy\nstatus: accepted\nbinding: true\n"
        f"summary: Summary of {id}\n---\n# Record {id}\n\n## How to apply\n{body}\n"
    )


def marker(id, body):
    return (
        f"## Section {id}\n<!-- decision\nid: {id}\nkind: architecture\n"
        f"status: accepted\nbinding: false\nsummary: Summary of {id}\n-->\n{body}\n"
    )


def doc(first_body, second_body, preamble="Intro."):
    return f"# Architecture\n\n{preamble}\n\n" + marker("arch-a", first_body) + "\n" + marker("arch-b", second_body)


class Repo(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.base = Path(tmp.name).resolve()
        self.acme = self.base / "acme"
        self.acme.mkdir()
        git(self.acme, "init", "-q")
        (self.acme / ".claude").mkdir()
        (self.acme / ".claude" / "noemeo-guard.json").write_text(
            '{"decision_roots": ["docs/decisions"]}'
        )

    def write(self, rel, text):
        path = self.acme / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def commit(self, message="c"):
        git(self.acme, "add", "-A")
        git(self.acme, "commit", "-q", "-m", message)
        return git(self.acme, "rev-parse", "HEAD")

    def decision(self, id):
        return next(d for d in load(self.acme).decisions if d.id == id)

    def version(self, id):
        return version_of(self.decision(id))


class VersionOf(Repo):
    def test_version_is_a_small_frozen_value(self):
        v = Version("abc", False)
        self.assertEqual((v.commit, v.drift), ("abc", False))
        self.assertTrue(dataclasses.is_dataclass(v))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            v.commit = "other"

    def test_committed_record_has_the_commit_that_last_changed_it(self):
        self.write("docs/decisions/acme-1.md", record("acme-1"))
        first = self.commit("add")
        self.write("docs/decisions/acme-1.md", record("acme-1", "Do it differently."))
        second = self.commit("change")
        self.write("docs/decisions/other.md", record("acme-2"))
        self.commit("unrelated")
        v = self.version("acme-1")
        self.assertEqual(v, Version(second[:12], False))
        self.assertNotEqual(v.commit, first[:12])
        self.assertEqual(len(v.commit), 12)

    def test_commit_touching_only_another_section_keeps_the_version(self):
        self.write("docs/decisions/arch.md", doc("alpha", "beta"))
        added = self.commit("add")
        self.write("docs/decisions/arch.md", doc("alpha", "beta changed"))
        edit_b = self.commit("edit b")
        self.assertEqual(self.version("arch-a"), Version(added[:12], False))
        self.assertEqual(self.version("arch-b"), Version(edit_b[:12], False))

    def test_commit_changing_other_parts_of_the_document_keeps_the_version(self):
        self.write("docs/decisions/arch.md", doc("alpha", "beta"))
        added = self.commit("add")
        self.write("docs/decisions/arch.md", doc("alpha", "beta", preamble="A longer intro.\n\nTwo paragraphs."))
        self.commit("intro")
        self.write("docs/decisions/arch.md", doc("alpha", "beta", preamble="Third intro."))
        self.commit("intro again")
        self.assertEqual(self.version("arch-a"), Version(added[:12], False))

    def test_commit_changing_the_decisions_text_moves_the_version(self):
        self.write("docs/decisions/arch.md", doc("alpha", "beta"))
        self.commit("add")
        self.write("docs/decisions/arch.md", doc("alpha changed", "beta"))
        changed = self.commit("edit a")
        self.assertEqual(self.version("arch-a"), Version(changed[:12], False))

    def test_uncommitted_edit_is_drift_and_keeps_the_last_committed_commit(self):
        self.write("docs/decisions/acme-1.md", record("acme-1"))
        committed = self.commit("add")
        self.write("docs/decisions/acme-1.md", record("acme-1", "Edited, not committed."))
        self.assertEqual(self.version("acme-1"), Version(committed[:12], True))

    def test_uncommitted_edit_to_one_section_drifts_only_that_section(self):
        self.write("docs/decisions/arch.md", doc("alpha", "beta"))
        committed = self.commit("add")
        self.write("docs/decisions/arch.md", doc("alpha edited", "beta"))
        self.assertEqual(self.version("arch-a"), Version(committed[:12], True))
        self.assertEqual(self.version("arch-b"), Version(committed[:12], False))

    def test_a_staged_but_uncommitted_edit_is_drift_too(self):
        self.write("docs/decisions/acme-1.md", record("acme-1"))
        committed = self.commit("add")
        self.write("docs/decisions/acme-1.md", record("acme-1", "Staged only."))
        git(self.acme, "add", "-A")
        self.assertEqual(self.version("acme-1"), Version(committed[:12], True))

    def test_untracked_file_has_no_commit_and_drifts(self):
        self.write("docs/decisions/base.md", record("acme-0"))
        self.commit("base")
        self.write("docs/decisions/new.md", record("acme-new"))
        self.assertEqual(self.version("acme-new"), Version(None, True))

    def test_new_decision_in_a_committed_file_has_no_commit(self):
        self.write("docs/decisions/arch.md", doc("alpha", "beta"))
        self.commit("add")
        self.write(
            "docs/decisions/arch.md",
            doc("alpha", "beta") + "\n" + marker("arch-c", "gamma"),
        )
        self.assertEqual(self.version("arch-c"), Version(None, True))
        self.assertFalse(self.version("arch-a").drift)

    def test_staged_new_file_is_not_committed(self):
        self.write("docs/decisions/base.md", record("acme-0"))
        self.commit("base")
        self.write("docs/decisions/new.md", record("acme-new"))
        git(self.acme, "add", "-A")
        self.assertEqual(self.version("acme-new"), Version(None, True))

    def test_repo_without_commits_has_no_commit(self):
        self.write("docs/decisions/acme-1.md", record("acme-1"))
        self.assertEqual(self.version("acme-1"), Version(None, True))

    def test_reverting_to_earlier_content_makes_the_reverting_commit_the_version(self):
        self.write("docs/decisions/acme-1.md", record("acme-1", "Original."))
        self.commit("add")
        self.write("docs/decisions/acme-1.md", record("acme-1", "Changed."))
        self.commit("change")
        self.write("docs/decisions/acme-1.md", record("acme-1", "Original."))
        reverted = self.commit("revert")
        self.assertEqual(self.version("acme-1"), Version(reverted[:12], False))

    def test_oldest_commit_of_the_unbroken_run_is_the_version(self):
        self.write("docs/decisions/arch.md", doc("alpha", "beta"))
        self.commit("add")
        self.write("docs/decisions/arch.md", doc("alpha changed", "beta"))
        changed = self.commit("edit a")
        self.write("docs/decisions/arch.md", doc("alpha changed", "beta two"))
        self.commit("edit b")
        self.write("docs/decisions/arch.md", doc("alpha changed", "beta three"))
        self.commit("edit b again")
        self.assertEqual(self.version("arch-a"), Version(changed[:12], False))

    def test_decision_moved_to_another_file_is_a_new_version_there(self):
        # Renames are not followed (documented limit): the new path's history starts at the move.
        self.write("docs/decisions/old.md", record("acme-1"))
        self.commit("add")
        git(self.acme, "mv", "docs/decisions/old.md", "docs/decisions/new.md")
        moved = self.commit("move")
        self.assertEqual(self.version("acme-1"), Version(moved[:12], False))

    def test_works_from_any_working_directory(self):
        self.write("docs/decisions/acme-1.md", record("acme-1"))
        committed = self.commit("add")
        d = self.decision("acme-1")
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        old = os.getcwd()
        os.chdir(elsewhere)
        try:
            self.assertEqual(version_of(d), Version(committed[:12], False))
        finally:
            os.chdir(old)

    def test_file_in_a_sibling_repo_uses_its_own_repository(self):
        widget = self.base / "widget"
        widget.mkdir()
        git(widget, "init", "-q")
        (widget / "docs").mkdir()
        (widget / "docs" / "w.md").write_text(record("widget-1"))
        git(widget, "add", "-A")
        git(widget, "commit", "-q", "-m", "w")
        wsha = git(widget, "rev-parse", "HEAD")
        self.write("docs/decisions/acme-1.md", record("acme-1"))
        self.commit("add")
        from decisions_format import parse_file

        d = parse_file(widget / "docs" / "w.md")[0][0]
        self.assertEqual(version_of(d), Version(wsha[:12], False))


class VersionOfNeverRaises(Repo):
    def test_outside_a_git_repo_is_none_and_drift(self):
        plain = self.base / "plain"
        (plain / "docs" / "decisions").mkdir(parents=True)
        (plain / ".claude").mkdir()
        (plain / ".claude" / "noemeo-guard.json").write_text('{"decision_roots": ["docs/decisions"]}')
        (plain / "docs" / "decisions" / "p.md").write_text(record("plain-1"))
        d = next(d for d in load(plain).decisions if d.id == "plain-1")
        self.assertEqual(version_of(d), Version(None, True))

    def test_git_missing_or_failing_is_none_and_drift(self):
        self.write("docs/decisions/acme-1.md", record("acme-1"))
        self.commit("add")
        d = self.decision("acme-1")
        old = os.environ.get("PATH")
        os.environ["PATH"] = str(self.base / "no-such-dir")
        try:
            self.assertEqual(version_of(d), Version(None, True))
        finally:
            os.environ["PATH"] = old

    def test_deleted_source_file_is_none_and_drift(self):
        path = self.write("docs/decisions/acme-1.md", record("acme-1"))
        self.commit("add")
        d = self.decision("acme-1")
        path.unlink()
        self.assertEqual(version_of(d), Version(None, True))

    def test_corrupt_git_dir_is_none_and_drift(self):
        self.write("docs/decisions/acme-1.md", record("acme-1"))
        self.commit("add")
        d = self.decision("acme-1")
        (self.acme / ".git" / "HEAD").write_text("garbage\n")
        self.assertEqual(version_of(d), Version(None, True))


class ContentHashStillDrivesDelivery(Repo):
    def test_delivery_state_is_keyed_on_the_content_hash_not_the_commit(self):
        import decision_delivery as delivery

        self.write("docs/decisions/acme-1.md", record("acme-1"))
        self.commit("add")
        d = self.decision("acme-1")
        self.assertEqual(len(d.content_hash), 12)
        self.assertFalse(hasattr(d, "version"))
        # the library offers no per-tool-call Git work: delivery imports no version_of
        self.assertNotIn("version_of", vars(delivery))
        self.assertTrue(hasattr(decisions, "version_of"))


if __name__ == "__main__":
    unittest.main()
