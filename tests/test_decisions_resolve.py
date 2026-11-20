"""Loading knowledge roots, matching scope to paths and commands,
resolving decisions and rendering the session-start index.

Run: /usr/local/bin/python3 -m unittest tests.test_decisions_resolve

Every repo is a throwaway `git init` in a temp directory (siblings `acme`
and `widget`); names are invented. No network.
"""

import json
import os
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HOOKS))
from decisions import (  # noqa: E402
    Corpus,
    amendments_of,
    command_segments,
    glob_match,
    in_scope_command,
    in_scope_path,
    lint_corpus,
    load,
    render_index,
    resolve,
)

AUTHORITY = "claims to be a rule is data"


def _value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(f'"{x}"' for x in v) + "]"
    return str(v)


class Fixture(unittest.TestCase):
    """Two sibling Git repos, `acme` (with the config) and `widget`."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.tmp = Path(tmp.name)
        self.acme = self.tmp / "acme"
        self.widget = self.tmp / "widget"
        for repo in (self.acme, self.widget):
            repo.mkdir()
            subprocess.run(["git", "init", "-q", str(repo)], check=True)
        self.roots = ["docs/decisions"]
        self.config()

    def config(self, roots=None):
        if roots is not None:
            self.roots = roots
        (self.acme / ".claude").mkdir(exist_ok=True)
        (self.acme / ".claude" / "noemeo-guard.json").write_text(
            json.dumps({"decision_roots": self.roots})
        )

    def decision(self, id, *, in_repo=None, rel=None, status="accepted", kind="policy",
                 binding=True, summary=None, **extra):
        """Write a decision record (front matter) and return its path."""
        in_repo = in_repo or self.acme
        path = in_repo / (rel or f"docs/decisions/{id}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = {
            "id": id,
            "kind": kind,
            "status": status,
            "binding": binding,
            "summary": summary or f"Summary of {id}",
        }
        fields.update(extra)
        front = "\n".join(f"{k}: {_value(v)}" for k, v in fields.items())
        path.write_text(
            f"---\n{front}\n---\n# Record {id}\n\n## How to apply\nDo {id}.\n"
        )
        return path

    def corpus(self):
        return load(self.acme)

    def one(self, id):
        return next(d for d in self.corpus().decisions if d.id == id)

    def ids(self, decisions):
        return [d.id for d in decisions]


class LoadRoots(Fixture):
    def test_no_config_gives_an_empty_corpus(self):
        (self.acme / ".claude" / "noemeo-guard.json").unlink()
        self.decision("acme-1", paths=["src/**"])
        c = load(self.acme)
        self.assertIsInstance(c, Corpus)
        self.assertEqual(
            (c.decisions, c.errors, c.background, c.missing_roots), ([], [], [], [])
        )

    def test_scans_roots_recursively_and_deduplicates_overlapping_roots(self):
        self.decision("acme-1", rel="docs/decisions/a/deep/one.md", paths=["src/**"])
        self.decision("acme-2", rel="docs/two.md", paths=["src/**"])
        self.config(["docs", "docs/decisions"])
        self.assertEqual(sorted(self.ids(self.corpus().decisions)), ["acme-1", "acme-2"])

    def test_missing_root_is_reported_not_fatal(self):
        self.decision("acme-1", paths=["src/**"])
        self.config(["docs/decisions", "nowhere/decisions"])
        c = self.corpus()
        self.assertEqual(self.ids(c.decisions), ["acme-1"])
        self.assertEqual(len(c.missing_roots), 1)
        self.assertIn("nowhere/decisions", c.missing_roots[0])

    def test_one_malformed_file_does_not_hide_the_others(self):
        self.decision("acme-1", paths=["src/**"])
        bad = self.acme / "docs/decisions/bad.md"
        bad.write_text("---\nid: acme-bad\nkind: nonsense\n---\n# Bad\n")
        c = self.corpus()
        self.assertEqual(self.ids(c.decisions), ["acme-1"])
        self.assertGreaterEqual(len(c.errors), 1)
        self.assertEqual({Path(e.path).name for e in c.errors}, {"bad.md"})

    def test_front_matter_without_id_and_plain_markdown_are_background(self):
        (self.acme / "docs/decisions").mkdir(parents=True)
        (self.acme / "docs/decisions/notes.md").write_text("# Plain notes\n\nText.\n")
        (self.acme / "docs/decisions/other.md").write_text(
            "---\ntitle: x\n---\n# Other doc\n"
        )
        c = self.corpus()
        self.assertEqual(c.decisions, [])
        self.assertEqual(c.errors, [])
        got = {Path(p).name: t for p, t in c.background}
        self.assertEqual(got, {"notes.md": "Plain notes", "other.md": "Other doc"})

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_unreadable_subdirectory_does_not_stop_loading(self):
        self.decision("acme-1", paths=["src/**"])
        self.decision("acme-2", rel="docs/decisions/locked/two.md", paths=["src/**"])
        locked = self.acme / "docs/decisions/locked"
        self.decision("acme-3", rel="docs/decisions/open/three.md", paths=["src/**"])
        os.chmod(locked, 0)
        self.addCleanup(os.chmod, locked, 0o755)
        c = self.corpus()  # must not raise
        self.assertEqual(sorted(self.ids(c.decisions)), ["acme-1", "acme-3"])

    def test_a_decision_file_is_not_also_background(self):
        self.decision("acme-1", paths=["src/**"])
        self.assertEqual(self.corpus().background, [])


class Glob(unittest.TestCase):
    def test_globs(self):
        cases = [
            ("src/**/*.py", "src/a.py", True),
            ("src/**/*.py", "src/x/y/a.py", True),
            ("src/**/*.py", "src/a.txt", False),
            ("src/*.py", "src/x/a.py", False),
            ("*.toml", "settings.toml", True),
            ("*.toml", "conf/settings.toml", False),
            ("**/x.py", "x.py", True),
            ("docs/**", "docs/a/b.md", True),
            ("docs/**", "other/a.md", False),
            ("a?.md", "ab.md", True),
            ("a?.md", "a/.md", False),
            ("a.b", "axb", False),  # dot is literal
        ]
        for pat, path, want in cases:
            self.assertEqual(glob_match(pat, path), want, (pat, path))


class Commands(Fixture):
    def test_segments_strip_env_and_sudo(self):
        self.assertEqual(
            command_segments("AWS_PROFILE=x aws s3 ls && cd a; sudo terraform plan"),
            ["aws s3 ls", "cd a", "terraform plan"],
        )

    def test_segments_split_on_every_separator(self):
        self.assertEqual(
            command_segments("a 1 && b 2 || c 3; d 4 | e 5\nf 6"),
            ["a 1", "b 2", "c 3", "d 4", "e 5", "f 6"],
        )

    def test_segments_split_on_substitutions(self):
        self.assertEqual(command_segments("echo `aws s3 ls`"), ["echo", "aws s3 ls"])
        self.assertEqual(command_segments("echo $(aws s3 ls)")[0], "echo")
        self.assertIn("aws s3 ls", [s.rstrip(")") for s in command_segments("echo $(aws s3 ls)")])

    def test_several_env_assignments_are_dropped(self):
        self.assertEqual(command_segments("A=1 B=2 aws s3 ls"), ["aws s3 ls"])

    def test_command_scope(self):
        self.decision("acme-1", commands=["aws *"])
        d = self.one("acme-1")
        self.assertTrue(in_scope_command(d, "aws s3 ls"))
        self.assertFalse(in_scope_command(d, "echo aws"))
        self.assertFalse(in_scope_command(d, "ls"))

    def test_command_scope_through_prefixes_and_chains(self):
        self.decision("acme-1", commands=["terraform *"])
        self.decision("acme-2", commands=["aws *"])
        tf, aws = self.one("acme-1"), self.one("acme-2")
        self.assertTrue(in_scope_command(tf, "cd infra && terraform plan"))
        self.assertTrue(in_scope_command(aws, "AWS_PROFILE=x aws s3 ls"))
        self.assertTrue(in_scope_command(aws, "sudo aws s3 ls"))
        self.assertTrue(in_scope_command(aws, "echo hi | aws s3 ls"))
        self.assertTrue(in_scope_command(aws, "echo `aws s3 ls`"))
        self.assertFalse(in_scope_command(aws, "cd infra && terraform plan"))
        self.assertFalse(in_scope_command(tf, "echo terraform plan"))

    def test_command_scope_bare_command_and_wrappers(self):
        self.decision("acme-1", commands=["terraform *"])
        tf = self.one("acme-1")
        for command in (
            "terraform",
            "env AWS_PROFILE=x terraform plan",
            "time terraform plan",
            "nohup terraform plan",
            "/usr/local/bin/terraform plan",
        ):
            with self.subTest(command):
                self.assertTrue(in_scope_command(tf, command))
        self.assertFalse(in_scope_command(tf, "echo terraform plan"))

    def test_decision_without_commands_never_matches_a_command(self):
        self.decision("acme-1", paths=["src/**"])
        self.assertFalse(in_scope_command(self.one("acme-1"), "aws s3 ls"))


class Paths(Fixture):
    def test_repo_defaults_to_the_decisions_own_repo(self):
        self.decision("acme-1", paths=["src/**"])
        d = self.one("acme-1")
        self.assertTrue(in_scope_path(d, self.acme / "src/a.py"))
        self.assertFalse(in_scope_path(d, self.widget / "src/a.py"))
        self.assertFalse(in_scope_path(d, self.acme / "lib/a.py"))

    def test_decision_in_another_repo_defaults_to_that_repo(self):
        self.decision("widget-1", in_repo=self.widget, paths=["src/**"])
        self.config(["docs/decisions", "../widget/docs/decisions"])
        d = self.one("widget-1")
        self.assertTrue(in_scope_path(d, self.widget / "src/a.py"))
        self.assertFalse(in_scope_path(d, self.acme / "src/a.py"))

    def test_repo_named_and_star(self):
        self.decision("acme-named", paths=["src/**"], repo="widget")
        self.decision("acme-star", paths=["src/**"], repo="*")
        named, star = self.one("acme-named"), self.one("acme-star")
        a, w = self.acme / "src/a.py", self.widget / "src/a.py"
        self.assertTrue(in_scope_path(named, w))
        self.assertFalse(in_scope_path(named, a))
        self.assertTrue(in_scope_path(star, a))
        self.assertTrue(in_scope_path(star, w))

    def test_path_outside_every_repo_or_through_symlink(self):
        self.decision("acme-1", paths=["src/**"])
        d = self.one("acme-1")
        (self.acme / "src").mkdir()
        (self.acme / "src/a.py").write_text("x = 1\n")
        outside = self.tmp / "elsewhere"
        outside.mkdir()
        (outside / "x.py").write_text("x = 1\n")
        link = outside / "link.py"
        link.symlink_to(self.acme / "src/a.py")
        self.assertFalse(in_scope_path(d, Path("/tmp/x.py")))
        self.assertFalse(in_scope_path(d, outside / "x.py"))
        self.assertFalse(in_scope_path(d, Path("src/a.py")))  # relative
        self.assertFalse(in_scope_path(d, Path("../src/a.py")))
        self.assertTrue(in_scope_path(d, link))

    def test_symlink_out_of_scope_does_not_match(self):
        self.decision("acme-1", paths=["src/**"])
        d = self.one("acme-1")
        (self.acme / "src").mkdir()
        (self.widget / "src").mkdir()
        (self.widget / "src/w.py").write_text("x = 1\n")
        (self.acme / "src/sneaky.py").symlink_to(self.widget / "src/w.py")
        self.assertFalse(in_scope_path(d, self.acme / "src/sneaky.py"))

    def test_a_file_that_does_not_exist_yet_is_matched_by_location(self):
        self.decision("acme-1", paths=["src/**"])
        d = self.one("acme-1")
        self.assertTrue(in_scope_path(d, self.acme / "src/new/dir/created.py"))
        self.assertFalse(in_scope_path(d, self.acme / "lib/new/created.py"))

    def test_dotdot_inside_a_path_is_resolved(self):
        self.decision("acme-1", paths=["src/**"])
        d = self.one("acme-1")
        self.assertFalse(in_scope_path(d, self.acme / "src/../lib/a.py"))
        self.assertTrue(in_scope_path(d, self.acme / "lib/../src/a.py"))

    def test_decision_without_paths_never_matches_a_path(self):
        self.decision("acme-1", commands=["aws *"])
        self.assertFalse(in_scope_path(self.one("acme-1"), self.acme / "src/a.py"))

    def test_path_in_a_directory_that_is_not_a_repo(self):
        self.decision("acme-1", paths=["**"], repo="*")
        d = self.one("acme-1")
        plain = self.tmp / "plain"
        plain.mkdir()
        # no repo, no match, no exception
        self.assertFalse(in_scope_path(d, plain / "a.py"))


class Resolve(Fixture):
    def test_only_current_decisions_are_resolved(self):
        for status in ("accepted", "temporary", "proposed", "open",
                       "superseded", "retired", "rejected"):
            self.decision(f"acme-{status}", status=status, paths=["src/**"])
        got = resolve(self.corpus(), paths=[self.acme / "src/a.py"])
        self.assertEqual(self.ids(got), ["acme-accepted", "acme-temporary"])

    def test_non_current_decisions_are_not_resolved_by_command_or_task(self):
        self.decision("acme-1", status="proposed", commands=["aws *"], tasks=["design"])
        c = self.corpus()
        self.assertEqual(resolve(c, commands=["aws s3 ls"]), [])
        self.assertEqual(resolve(c, tasks=["design"]), [])

    def test_resolves_by_path_command_and_task(self):
        self.decision("acme-p", paths=["src/**"])
        self.decision("acme-c", commands=["aws *"])
        self.decision("acme-t", tasks=["design"])
        c = self.corpus()
        self.assertEqual(self.ids(resolve(c, paths=[self.acme / "src/a.py"])), ["acme-p"])
        self.assertEqual(self.ids(resolve(c, commands=["AWS_PROFILE=x aws s3 ls"])), ["acme-c"])
        self.assertEqual(self.ids(resolve(c, tasks=["design"])), ["acme-t"])
        self.assertEqual(resolve(c, tasks=["review"]), [])
        self.assertEqual(resolve(c), [])

    def test_results_are_sorted_by_id_and_listed_once(self):
        self.decision("acme-3", paths=["src/**"], commands=["aws *"])
        self.decision("acme-1", paths=["src/**"])
        got = resolve(
            self.corpus(),
            paths=[self.acme / "src/a.py", self.acme / "src/b.py"],
            commands=["aws s3 ls"],
        )
        self.assertEqual(self.ids(got), ["acme-1", "acme-3"])

    def test_current_amendment_follows_its_original(self):
        self.decision("acme-a", paths=["src/**"])
        self.decision("acme-b", amends=["acme-a"])  # no scope of its own
        c = self.corpus()
        got = resolve(c, paths=[self.acme / "src/a.py"])
        self.assertEqual(self.ids(got), ["acme-a", "acme-b"])
        self.assertEqual(self.ids(amendments_of(c, self.one("acme-a"))), ["acme-b"])
        self.assertEqual(amendments_of(c, self.one("acme-b")), [])

    def test_amendment_stays_with_its_original_whatever_its_id(self):
        self.decision("acme-5", paths=["src/**"])
        self.decision("acme-3", paths=["src/**"])
        self.decision("acme-1", amends=["acme-5"])
        got = resolve(self.corpus(), paths=[self.acme / "src/a.py"])
        self.assertEqual(self.ids(got), ["acme-3", "acme-5", "acme-1"])

    def test_amendment_alone_is_not_resolved_without_its_original(self):
        self.decision("acme-a", paths=["src/**"])
        self.decision("acme-b", amends=["acme-a"])
        self.assertEqual(resolve(self.corpus(), paths=[self.acme / "lib/a.py"]), [])

    def test_amendment_that_is_not_current_is_not_delivered(self):
        self.decision("acme-a", paths=["src/**"])
        self.decision("acme-b", amends=["acme-a"], status="proposed")
        self.decision("acme-c", amends=["acme-a"], status="retired")
        c = self.corpus()
        self.assertEqual(amendments_of(c, self.one("acme-a")), [])
        self.assertEqual(self.ids(resolve(c, paths=[self.acme / "src/a.py"])), ["acme-a"])

    def test_amendment_in_scope_and_following_is_not_listed_twice(self):
        self.decision("acme-a", paths=["src/**"])
        self.decision("acme-b", amends=["acme-a"], paths=["src/**"])
        got = resolve(self.corpus(), paths=[self.acme / "src/a.py"])
        self.assertEqual(self.ids(got), ["acme-a", "acme-b"])

    def test_always_decisions_are_always_resolved(self):
        self.decision("acme-1", always=True)
        self.decision("acme-2", always=True, status="proposed")
        self.decision("acme-3", paths=["src/**"])
        c = self.corpus()
        self.assertEqual(self.ids(resolve(c)), ["acme-1"])
        self.assertEqual(
            self.ids(resolve(c, paths=[self.acme / "src/a.py"])), ["acme-1", "acme-3"]
        )

    def test_folder_does_not_set_scope(self):
        self.config(["knowledge"])
        self.decision("acme-fe", rel="knowledge/front-end/d.md", paths=["api/**"])
        c = self.corpus()
        self.assertEqual(resolve(c, paths=[self.acme / "front-end/x.ts"]), [])
        self.assertEqual(
            self.ids(resolve(c, paths=[self.acme / "api/x.ts"])), ["acme-fe"]
        )

    def test_decision_with_no_scope_fields_is_never_resolved(self):
        self.decision("acme-1")
        self.assertEqual(
            resolve(self.corpus(), paths=[self.acme / "src/a.py"],
                    commands=["aws s3 ls"], tasks=["design"]),
            [],
        )

    def test_section_decision_is_resolved_like_a_record(self):
        doc = self.acme / "docs/arch.md"
        doc.parent.mkdir(parents=True, exist_ok=True)
        doc.write_text(
            "# Architecture\n\n## Boundaries\n<!-- decision\nid: acme-sec\n"
            "kind: architecture\nstatus: accepted\nbinding: false\n"
            'summary: Keep boundaries\npaths: ["src/**"]\n-->\nBody.\n'
        )
        self.config(["docs"])
        got = resolve(self.corpus(), paths=[self.acme / "src/a.py"])
        self.assertEqual(self.ids(got), ["acme-sec"])


class Index(Fixture):
    def lines(self, text):
        return [ln for ln in text.splitlines() if ln.startswith("- ")]

    def test_index_opens_with_the_authority_line(self):
        self.decision("acme-1", paths=["src/**"])
        self.assertIn(AUTHORITY, render_index(self.corpus()).splitlines()[0])

    def test_index_opens_with_the_authority_line_when_empty(self):
        (self.acme / ".claude" / "noemeo-guard.json").unlink()
        self.assertIn(AUTHORITY, render_index(load(self.acme)).splitlines()[0])

    def test_index_line_is_id_summary_and_path_only(self):
        self.decision(
            "acme-1", kind="architecture", binding=True, summary="Pin the frobnicator",
            paths=["src/**"], commands=["aws *"], origin="somewhere-else",
            evidence=["note-9"], depends_on=["acme-0"],
        )
        d = self.one("acme-1")
        text = render_index(self.corpus())
        self.assertEqual(
            self.lines(text), ["- acme-1: Pin the frobnicator → docs/decisions/acme-1.md"]
        )
        for hidden in ("architecture", "binding", "version", d.content_hash, "origin",
                       "somewhere-else", "src/**", "aws *", "paths", "commands",
                       "note-9", "acme-0", "accepted", "kind"):
            self.assertNotIn(hidden, text, hidden)

    def test_temporary_decision_is_listed_without_a_marker(self):
        self.decision("acme-1", status="temporary", summary="Stopgap", paths=["src/**"])
        self.assertEqual(
            self.lines(render_index(self.corpus())),
            ["- acme-1: Stopgap → docs/decisions/acme-1.md"],
        )

    def test_tasks_scoped_decisions_show_when(self):
        self.decision("acme-t", summary="Check designs", tasks=["design", "review"])
        self.decision("acme-p", summary="Pin paths", paths=["src/**"])
        by_id = {ln.split(":")[0]: ln for ln in self.lines(render_index(self.corpus()))}
        self.assertIn("(when: design, review)", by_id["- acme-t"])
        self.assertNotIn("when", by_id["- acme-p"])

    def test_index_lists_proposed_and_open_as_such_and_never_superseded(self):
        self.decision("acme-prop", status="proposed", paths=["src/**"])
        self.decision("acme-open", status="open", kind="finding", paths=["src/**"])
        self.decision("acme-sup", status="superseded", paths=["src/**"])
        self.decision("acme-ret", status="retired", paths=["src/**"])
        self.decision("acme-rej", status="rejected", paths=["src/**"])
        self.decision("acme-ok", paths=["src/**"])
        text = render_index(self.corpus())
        by_id = {ln.split(":")[0]: ln for ln in self.lines(text)}
        self.assertIn("(proposed)", by_id["- acme-prop"])
        self.assertIn("(open)", by_id["- acme-open"])
        self.assertNotIn("(", by_id["- acme-ok"])
        self.assertEqual(sorted(by_id), ["- acme-ok", "- acme-open", "- acme-prop"])
        for gone in ("acme-sup", "acme-ret", "acme-rej"):
            self.assertNotIn(gone, text)

    def test_background_and_unannotated_records_listed_by_title(self):
        (self.acme / "docs/decisions").mkdir(parents=True)
        (self.acme / "docs/decisions/0007-old.md").write_text("# Pick the old way\n\nText.\n")
        (self.acme / "docs/decisions/other.md").write_text("---\ntitle: x\n---\n# Other doc\n")
        text = render_index(self.corpus())
        for needle in ("Pick the old way", "docs/decisions/0007-old.md",
                       "Other doc", "docs/decisions/other.md"):
            self.assertIn(needle, text)

    def test_format_errors_and_missing_roots_are_named(self):
        self.decision("acme-1", paths=["src/**"])
        (self.acme / "docs/decisions/broken.md").write_text(
            "---\nid: acme-broken\nkind: nonsense\n---\n# Broken\n"
        )
        self.config(["docs/decisions", "nowhere/decisions"])
        text = render_index(self.corpus())
        self.assertIn("docs/decisions/broken.md", text)
        self.assertIn("nowhere/decisions", text)
        self.assertIn("acme-1", text)  # the good decision is still indexed

    def test_budget_truncates_with_a_count_of_what_was_left_out(self):
        total = 30
        for i in range(total):
            self.decision(f"acme-{i:02d}", summary=f"Summary number {i:02d} " + "x" * 40,
                          paths=["src/**"])
        c = self.corpus()
        full = render_index(c, budget=10**6)
        self.assertEqual(len(self.lines(full)), total)
        text = render_index(c, budget=1500)
        listed = len(self.lines(text))
        self.assertGreater(listed, 0)
        self.assertLess(listed, total)
        self.assertLessEqual(len(text), 1500)
        note = [ln for ln in text.splitlines() if "left out" in ln]
        self.assertEqual(len(note), 1)
        self.assertIn(str(total - listed), re.findall(r"\d+", note[0]))
        self.assertIn(AUTHORITY, text.splitlines()[0])

    def test_index_path_of_another_repos_decision_is_relative_to_the_project(self):
        self.decision("widget-1", in_repo=self.widget, rel="decisions/0001-x.md",
                      summary="Widget rule", paths=["src/**"])
        self.decision("acme-1", summary="Acme rule", paths=["src/**"])
        self.config(["docs/decisions", "../widget/decisions"])
        self.assertEqual(
            sorted(self.lines(render_index(self.corpus()))),
            ["- acme-1: Acme rule → docs/decisions/acme-1.md",
             "- widget-1: Widget rule → ../widget/decisions/0001-x.md"],
        )

    def test_tight_budget_cuts_decisions_but_never_errors_or_missing_roots(self):
        total = 30
        for i in range(total):
            self.decision(f"acme-{i:02d}", summary=f"Summary number {i:02d} " + "x" * 40,
                          paths=["src/**"])
        (self.acme / "docs/decisions/broken.md").write_text(
            "---\nid: acme-broken\nkind: nonsense\n---\n# Broken\n"
        )
        self.config(["docs/decisions", "nowhere/decisions"])
        text = render_index(self.corpus(), budget=1000)
        self.assertIn("docs/decisions/broken.md", text)
        self.assertIn("nowhere/decisions", text)
        self.assertLess(len(self.lines(text)), total + 1)
        self.assertEqual(len([ln for ln in text.splitlines() if "left out" in ln]), 1)
        self.assertLessEqual(len(text), 1000)


class Worktrees(Fixture):
    def setUp(self):
        super().setUp()
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "x"],
                       cwd=self.acme, check=True)
        self.wt = self.tmp / "acme-wt"
        subprocess.run(["git", "worktree", "add", "-q", "-b", "wt", str(self.wt)],
                       cwd=self.acme, check=True)

    def load_wt(self, **extra):
        self.decision("acme-1", in_repo=self.wt, paths=["src/**"], **extra)
        (self.wt / ".claude").mkdir(exist_ok=True)
        (self.wt / ".claude" / "noemeo-guard.json").write_text(
            json.dumps({"decision_roots": ["docs/decisions"]})
        )
        return next(d for d in load(self.wt).decisions if d.id == "acme-1")

    def test_default_repo_is_the_main_repository_not_the_checkout(self):
        d = self.load_wt()
        self.assertTrue(in_scope_path(d, self.wt / "src/a.py"))
        self.assertTrue(in_scope_path(d, self.acme / "src/a.py"))
        self.assertFalse(in_scope_path(d, self.widget / "src/a.py"))

    def test_repo_named_for_the_main_repository_matches_the_worktree(self):
        d = self.load_wt(repo="acme")
        self.assertTrue(in_scope_path(d, self.wt / "src/a.py"))
        self.assertTrue(in_scope_path(d, self.acme / "src/a.py"))

    def test_repo_named_for_another_repository_does_not_match_the_worktree(self):
        d = self.load_wt(repo="widget")
        self.assertFalse(in_scope_path(d, self.wt / "src/a.py"))
        self.assertTrue(in_scope_path(d, self.widget / "src/a.py"))


class NestedWorktrees(Fixture):
    """A linked worktree two levels down (`.worktrees/acme/wt`), so `../shared`
    from it does not reach the sibling that sits beside the main checkout."""

    def setUp(self):
        super().setUp()
        git = ["git", "-c", "user.name=t", "-c", "user.email=t@example.invalid"]
        subprocess.run(git + ["commit", "-q", "--allow-empty", "-m", "x"],
                       cwd=self.acme, check=True)
        self.wt = self.tmp / ".worktrees" / "acme" / "wt"
        self.wt.parent.mkdir(parents=True)
        subprocess.run(["git", "worktree", "add", "-q", "-b", "wt", str(self.wt)],
                       cwd=self.acme, check=True)
        self.shared = self.tmp / "shared"

    def config_wt(self, roots):
        (self.wt / ".claude").mkdir(exist_ok=True)
        (self.wt / ".claude" / "noemeo-guard.json").write_text(
            json.dumps({"decision_roots": roots})
        )

    def ids_wt(self, c):
        return sorted(d.id for d in c.decisions)

    def test_sibling_root_is_read_beside_the_main_checkout(self):
        self.decision("shared-1", in_repo=self.shared, rel="decisions/s1.md", paths=["src/**"])
        self.config_wt(["../shared/decisions"])
        self.assertFalse((self.wt / "../shared").resolve().exists())
        c = load(self.wt)
        self.assertEqual(self.ids_wt(c), ["shared-1"])
        self.assertEqual(c.missing_roots, [])

    def test_sibling_root_with_dotdot_inside_is_normalised(self):
        self.decision("shared-1", in_repo=self.shared, rel="decisions/s1.md", paths=["src/**"])
        self.config_wt(["../shared/x/../decisions"])
        self.assertEqual(self.ids_wt(load(self.wt)), ["shared-1"])

    def test_root_inside_the_checkout_is_read_from_the_worktree_not_main(self):
        self.decision("wt-only", in_repo=self.wt, paths=["src/**"])
        self.decision("main-only", in_repo=self.acme, paths=["src/**"])
        self.config_wt(["docs/decisions"])
        self.assertEqual(self.ids_wt(load(self.wt)), ["wt-only"])

    def test_inside_and_sibling_roots_together(self):
        self.decision("wt-only", in_repo=self.wt, paths=["src/**"])
        self.decision("shared-1", in_repo=self.shared, rel="decisions/s1.md", paths=["src/**"])
        self.config_wt(["docs/decisions", "../shared/decisions"])
        c = load(self.wt)
        self.assertEqual(self.ids_wt(c), ["shared-1", "wt-only"])
        self.assertEqual(c.missing_roots, [])

    def test_sibling_beside_the_worktree_only_is_not_read_and_is_reported_missing(self):
        # Pinned behaviour: a sibling root is always looked up beside the main
        # checkout; one that exists only beside the worktree is reported missing.
        beside_wt = self.wt.parent / "shared"
        self.decision("beside-wt", in_repo=beside_wt, rel="decisions/s.md", paths=["src/**"])
        self.config_wt(["../shared/decisions"])
        c = load(self.wt)
        self.assertEqual(c.decisions, [])
        self.assertEqual(c.missing_roots, ["../shared/decisions"])

    def test_missing_sibling_is_reported_when_absent_everywhere(self):
        self.config_wt(["../nowhere/decisions"])
        self.assertEqual(load(self.wt).missing_roots, ["../nowhere/decisions"])

    def test_absolute_root_is_unchanged(self):
        self.decision("shared-1", in_repo=self.shared, rel="decisions/s1.md", paths=["src/**"])
        self.config_wt([str(self.shared / "decisions")])
        c = load(self.wt)
        self.assertEqual(self.ids_wt(c), ["shared-1"])
        self.assertEqual(c.missing_roots, [])

    def test_absolute_root_that_does_not_exist_is_missing(self):
        self.config_wt([str(self.tmp / "gone" / "decisions")])
        self.assertEqual(len(load(self.wt).missing_roots), 1)

    def test_in_repo_root_that_is_a_symlink_to_outside_stays_the_worktrees_own(self):
        target = self.tmp / "elsewhere" / "decisions"
        self.decision("linked-1", in_repo=self.tmp / "elsewhere", rel="decisions/l.md",
                      paths=["src/**"])
        (self.wt / "docs").mkdir()
        (self.wt / "docs" / "linked").symlink_to(target)
        self.config_wt(["docs/linked"])
        c = load(self.wt)
        self.assertEqual(self.ids_wt(c), ["linked-1"])
        self.assertEqual(c.missing_roots, [])

    def test_session_start_index_from_the_worktree_lists_the_sibling_decision(self):
        self.decision("shared-1", in_repo=self.shared, rel="decisions/s1.md",
                      summary="Shared rule", paths=["src/**"])
        self.config_wt(["../shared/decisions"])
        text = render_index(load(self.wt))
        self.assertIn("- shared-1: Shared rule", text)
        self.assertNotIn("configured root not found", text)

    def test_lint_from_the_worktree_does_not_flag_the_sibling_root_missing(self):
        self.decision("shared-1", in_repo=self.shared, rel="decisions/s1.md", paths=["src/**"])
        self.config_wt(["../shared/decisions"])
        errors, warnings = lint_corpus(load(self.wt), self.wt)
        self.assertEqual([m for m in errors + warnings if "shared/decisions" in m and "not found" in m.lower()], [])
        self.assertEqual(load(self.wt).missing_roots, [])


class NormalCheckoutSiblingRoots(Fixture):
    def test_sibling_root_resolves_relative_to_the_repo(self):
        self.decision("widget-1", in_repo=self.widget, rel="decisions/w.md", paths=["src/**"])
        self.config(["../widget/decisions"])
        c = load(self.acme)
        self.assertEqual([d.id for d in c.decisions], ["widget-1"])
        self.assertEqual(c.missing_roots, [])

    def test_missing_sibling_root_is_reported(self):
        self.config(["../nowhere/decisions"])
        self.assertEqual(load(self.acme).missing_roots, ["../nowhere/decisions"])

    def test_absolute_root_is_unchanged(self):
        self.decision("widget-1", in_repo=self.widget, rel="decisions/w.md", paths=["src/**"])
        self.config([str(self.widget / "decisions")])
        self.assertEqual([d.id for d in load(self.acme).decisions], ["widget-1"])


if __name__ == "__main__":
    unittest.main()
