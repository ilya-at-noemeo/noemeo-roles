"""The decisions command line (index, resolve, deps, show, lint), the
`lint_corpus` library function, and what each prints.

Run: /usr/local/bin/python3 -m unittest tests.test_decisions_cli

Every repo is a throwaway `git init` in a temp directory; names are
invented (`acme`). The CLI runs as a subprocess, the way a person or a
hook runs it. No network.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
CLI = HOOKS / "decisions.py"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HOOKS))
import decisions  # noqa: E402
from decisions import load  # noqa: E402


def _value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(f'"{x}"' for x in v) + "]"
    return str(v)


def record(id, *, status="accepted", summary=None, how=True, **extra):
    """Text of a decision record with front matter."""
    fields = {
        "id": id,
        "kind": "policy",
        "status": status,
        "binding": True,
        "summary": f"Summary of {id}" if summary is None else summary,
    }
    fields.update(extra)
    front = "\n".join(f"{k}: {_value(v)}" for k, v in fields.items())
    body = f"# Record {id}\n\n## Context\nWhy {id}.\n"
    if how:
        body += f"\n## How to apply\nDo {id}.\n"
    return f"---\n{front}\n---\n{body}"


def git(repo, *args):
    return subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.strip()


class CliCase(unittest.TestCase):
    """One repo, `acme`, with a clean decision corpus, committed."""

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.acme = Path(tmp.name).resolve() / "acme"
        self.acme.mkdir()
        git(self.acme, "init", "-q")
        (self.acme / ".claude").mkdir()
        (self.acme / ".claude" / "noemeo-guard.json").write_text(
            json.dumps({"decision_roots": ["docs/decisions", "docs/more"]})
        )
        self.write("src/app.py", "print('acme')\n")
        self.write("docs/decisions/acme-1.md", record("acme-1", paths=["src/**"]))
        self.write(
            "docs/decisions/acme-2.md",
            record("acme-2", amends=["acme-1"], depends_on=["acme-1"]),
        )
        self.write("docs/more/acme-3.md", record("acme-3", commands=["terraform *"]))
        self.write("docs/decisions/notes.md", "# Plain notes\n\nJust notes.\n")
        git(self.acme, "add", "-A")
        git(self.acme, "commit", "-q", "-m", "base")

    def write(self, rel, text):
        path = self.acme / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text)
        return path

    def cli(self, *args, project=True, env_project=None):
        env = dict(os.environ)
        env.pop("CLAUDE_PROJECT_DIR", None)
        if project:
            env["CLAUDE_PROJECT_DIR"] = str(env_project or self.acme)
        return subprocess.run(
            [sys.executable, str(CLI), *args],
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.acme.parent),
        )

    def lint_with(self, files):
        """Lint with extra files written, then remove them again."""
        paths = [self.write(rel, text) for rel, text in files.items()]
        try:
            return self.cli("lint")
        finally:
            for p in paths:
                p.unlink()

    @staticmethod
    def lines(proc, prefix):
        return [ln for ln in proc.stdout.splitlines() if ln.startswith(prefix)]

    def has_line(self, proc, prefix, *needles):
        return any(all(n in ln for n in needles) for ln in self.lines(proc, prefix))


class Index(CliCase):
    def test_index_prints_each_decision_with_summary_and_path(self):
        proc = self.cli("index")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("- acme-1: Summary of acme-1 → docs/decisions/acme-1.md", proc.stdout)
        self.assertIn("- acme-3: Summary of acme-3 → docs/more/acme-3.md", proc.stdout)

    def test_project_option_replaces_the_environment_variable(self):
        other = self.acme.parent / "elsewhere"
        other.mkdir()
        for argv in (
            ["--project", str(self.acme), "index"],
            ["index", "--project", str(self.acme)],
        ):
            with self.subTest(argv=argv):
                proc = self.cli(*argv, env_project=other)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                self.assertIn("- acme-1: Summary of acme-1", proc.stdout)

    def test_a_malformed_file_is_named_not_fatal(self):
        self.write("docs/decisions/bad.md", "---\nid: acme-bad\nkind: nonsense\n---\n# Bad\n")
        proc = self.cli("index")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("bad.md", proc.stdout)
        self.assertIn("acme-1", proc.stdout)


class Lint(CliCase):
    def test_clean_corpus(self):
        proc = self.cli("lint")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.lines(proc, "error:"), [])
        self.assertEqual(self.lines(proc, "warning:"), [])

    def test_superseding_a_decision_that_is_still_current_is_an_error(self):
        for old_status in ("accepted", "temporary"):
            with self.subTest(old_status):
                proc = self.lint_with({
                    "docs/decisions/y.md": record("acme-y", status=old_status),
                    "docs/decisions/x.md": record("acme-x", supersedes=["acme-y"]),
                })
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertTrue(self.has_line(proc, "error:", "acme-x", "acme-y"), proc.stdout)
        proc = self.lint_with({
            "docs/decisions/y.md": record("acme-y", status="superseded"),
            "docs/decisions/x.md": record("acme-x", supersedes=["acme-y"]),
        })
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)

    def test_errors(self):
        cases = {
            "duplicate id across roots": (
                {"docs/more/dup.md": record("acme-1")},
                ("dup.md", "acme-1"),
            ),
            "format error": (
                {"docs/decisions/bad.md": "---\nid: acme-bad\nkind: nonsense\n---\n# Bad\n"},
                ("bad.md",),
            ),
            "dangling depends_on": (
                {"docs/decisions/d1.md": record("acme-d1", depends_on=["acme-404"])},
                ("d1.md", "acme-d1", "acme-404"),
            ),
            "dangling supersedes": (
                {"docs/decisions/d2.md": record("acme-d2", supersedes=["acme-405"])},
                ("d2.md", "acme-d2", "acme-405"),
            ),
            "dangling amends": (
                {"docs/decisions/d3.md": record("acme-d3", amends=["acme-406"])},
                ("d3.md", "acme-d3", "acme-406"),
            ),
            "depends on a superseded decision": (
                {
                    "docs/decisions/old.md": record("acme-old", status="superseded"),
                    "docs/decisions/new.md": record("acme-new", depends_on=["acme-old"]),
                },
                ("new.md", "acme-new", "acme-old"),
            ),
            "depends on a retired decision": (
                {
                    "docs/decisions/gone.md": record("acme-gone", status="retired"),
                    "docs/decisions/user.md": record("acme-user", depends_on=["acme-gone"]),
                },
                ("user.md", "acme-user", "acme-gone"),
            ),
        }
        for name, (files, needles) in cases.items():
            with self.subTest(name):
                proc = self.lint_with(files)
                self.assertEqual(proc.returncode, 1, proc.stdout + proc.stderr)
                self.assertTrue(
                    self.has_line(proc, "error:", *needles),
                    f"no error line with {needles}:\n{proc.stdout}",
                )

    def test_a_non_current_decision_may_depend_on_a_superseded_one(self):
        proc = self.lint_with(
            {
                "docs/decisions/old.md": record("acme-old", status="superseded"),
                "docs/decisions/prop.md": record(
                    "acme-prop", status="proposed", depends_on=["acme-old"]
                ),
            }
        )
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(self.lines(proc, "error:"), [])

    def test_warnings_do_not_fail(self):
        cases = {
            "record without front matter": (
                {"docs/decisions/0007-old-record.md": "# Old record\n\nSome text.\n"},
                "0007-old-record.md",
            ),
            "paths matching no tracked file": (
                {"docs/decisions/ghost.md": record("acme-ghost", paths=["ghost/**"])},
                "acme-ghost",
            ),
            "original whose amendment is no longer current": (
                {
                    "docs/decisions/orig.md": record("acme-orig"),
                    "docs/decisions/am.md": record(
                        "acme-am", status="retired", amends=["acme-orig"]
                    ),
                },
                "acme-orig",
            ),
            "empty delivered text": (
                {"docs/decisions/empty.md": record("acme-empty", how=False)},
                "acme-empty",
            ),
            "empty summary": (
                {"docs/decisions/nosum.md": record("acme-nosum", summary='""')},
                "acme-nosum",
            ),
        }
        for name, (files, needle) in cases.items():
            with self.subTest(name):
                proc = self.lint_with(files)
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertEqual(self.lines(proc, "error:"), [])
                self.assertTrue(
                    self.has_line(proc, "warning:", needle),
                    f"no warning line with {needle!r}:\n{proc.stdout}",
                )

    def test_a_deliver_list_that_finds_text_is_not_an_empty_record(self):
        text = record("acme-del", how=False, deliver=["Context"])
        proc = self.lint_with({"docs/decisions/del.md": text})
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertFalse(self.has_line(proc, "warning:", "acme-del"), proc.stdout)

    def test_lint_corpus_returns_errors_and_warnings_as_strings(self):
        self.write("docs/more/dup.md", record("acme-1"))
        self.write("docs/decisions/ghost.md", record("acme-ghost", paths=["ghost/**"]))
        errors, warnings = decisions.lint_corpus(load(self.acme), self.acme)
        self.assertTrue(errors and all(isinstance(e, str) for e in errors))
        self.assertTrue(warnings and all(isinstance(w, str) for w in warnings))
        self.assertTrue(any("acme-1" in e for e in errors), errors)
        self.assertTrue(any("acme-ghost" in w for w in warnings), warnings)
        self.assertFalse(any("acme-ghost" in e for e in errors), errors)

    def test_lint_corpus_on_a_clean_corpus_is_empty(self):
        self.assertEqual(decisions.lint_corpus(load(self.acme), self.acme), ([], []))


class InstructionFileReferences(CliCase):
    """Lint checks the decision ids that CLAUDE.md and AGENTS.md mention.

    One home per rule: an instruction file may point at a decision by id,
    never at one that is no longer current, and never by bare number.
    """

    def setUp(self):
        super().setUp()
        for id, status, extra in (
            ("acme-0007", "superseded", {}),
            ("acme-0008", "accepted", {"supersedes": ["acme-0007"]}),
            ("acme-0009", "retired", {}),
            ("acme-0010", "rejected", {}),
            ("acme-0011", "proposed", {}),
            ("acme-0012", "open", {}),
            ("acme-0013", "temporary", {}),
            ("0005", "accepted", {}),
        ):
            self.write(f"docs/decisions/{id}.md", record(id, status=status, **extra))
        git(self.acme, "add", "-A")
        git(self.acme, "commit", "-q", "-m", "more decisions")

    def lint_notes(self, files):
        proc = self.lint_with(files)
        self.assertIn(proc.returncode, (0, 1), proc.stdout + proc.stderr)
        return proc

    def test_a_superseded_reference_is_an_error_naming_file_line_status_and_successor(self):
        proc = self.lint_notes({"CLAUDE.md": "# Acme\n\nBuild with make.\nSee acme-0007 for hosting.\n"})
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn(
            "error: CLAUDE.md:4: refers to acme-0007, which is superseded; superseded by acme-0008",
            proc.stdout.splitlines(),
        )

    def test_superseded_without_a_current_successor_has_no_superseded_by_clause(self):
        self.write("docs/decisions/acme-0014.md", record("acme-0014", status="superseded"))
        proc = self.lint_notes({"CLAUDE.md": "See acme-0014.\n"})
        self.assertIn("error: CLAUDE.md:1: refers to acme-0014, which is superseded", proc.stdout.splitlines())

    def test_retired_and_rejected_references_are_errors(self):
        proc = self.lint_notes({"CLAUDE.md": "acme-0009 here\nand acme-0010 there\n"})
        self.assertEqual(proc.returncode, 1, proc.stdout)
        self.assertIn("error: CLAUDE.md:1: refers to acme-0009, which is retired", proc.stdout.splitlines())
        self.assertIn("error: CLAUDE.md:2: refers to acme-0010, which is rejected", proc.stdout.splitlines())

    def test_proposed_and_open_references_are_warnings_not_errors(self):
        proc = self.lint_notes({"CLAUDE.md": "acme-0011\nacme-0012\n"})
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn(
            "warning: CLAUDE.md:1: refers to acme-0011, which is proposed, not accepted",
            proc.stdout.splitlines(),
        )
        self.assertIn(
            "warning: CLAUDE.md:2: refers to acme-0012, which is open, not accepted",
            proc.stdout.splitlines(),
        )
        self.assertFalse(self.lines(proc, "error:"), proc.stdout)

    def test_references_to_accepted_and_temporary_decisions_are_silent(self):
        proc = self.lint_notes({"CLAUDE.md": "acme-1 acme-0008 acme-0013 acme-3\n"})
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertFalse(self.has_line(proc, "error:", "CLAUDE.md"), proc.stdout)
        self.assertFalse(self.has_line(proc, "warning:", "CLAUDE.md"), proc.stdout)

    def test_nested_agents_md_and_dot_claude_claude_md_are_checked(self):
        proc = self.lint_notes({
            "services/api/AGENTS.md": "x\nacme-0007\n",
            ".claude/CLAUDE.md": "acme-0009\n",
        })
        self.assertTrue(
            self.has_line(proc, "error:", "services/api/AGENTS.md:2: refers to acme-0007"), proc.stdout
        )
        self.assertTrue(
            self.has_line(proc, "error:", ".claude/CLAUDE.md:1: refers to acme-0009"), proc.stdout
        )

    def test_an_id_inside_a_longer_token_is_not_a_reference(self):
        text = "acme-00071 xacme-0007 acme-0007x acme-0007-b acme_0007 ACME-0007 acme-0007_\n"
        proc = self.lint_notes({"CLAUDE.md": text})
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertFalse(self.has_line(proc, "error:", "CLAUDE.md"), proc.stdout)

    def test_an_id_beside_punctuation_is_a_reference_even_in_a_code_span(self):
        proc = self.lint_notes({"CLAUDE.md": "Why: (acme-0007), `acme-0007`.\n"})
        self.assertTrue(self.has_line(proc, "error:", "CLAUDE.md:1: refers to acme-0007"), proc.stdout)

    def test_a_decision_number_that_is_not_an_id_gets_one_warning_per_line(self):
        proc = self.lint_notes({
            "CLAUDE.md": "Why: decision 0008.\nSee decisions 0006 and 0016, and Decision 0017 too.\nplain\n",
        })
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertIn(
            'warning: CLAUDE.md:1: refers to a decision by number ("decision 0008"); '
            "use its id so lint can check it",
            proc.stdout.splitlines(),
        )
        on_line_2 = [ln for ln in self.lines(proc, "warning:") if "CLAUDE.md:2:" in ln]
        self.assertEqual(len(on_line_2), 1, proc.stdout)
        self.assertIn("by number", on_line_2[0])
        self.assertFalse(self.has_line(proc, "warning:", "CLAUDE.md:3:"), proc.stdout)

    def test_a_decision_number_equal_to_a_known_id_is_not_a_numbered_warning(self):
        proc = self.lint_notes({"CLAUDE.md": "See decision 0005.\n"})
        self.assertFalse(self.has_line(proc, "warning:", "by number"), proc.stdout)
        self.assertFalse(self.has_line(proc, "error:", "CLAUDE.md"), proc.stdout)

    def test_the_second_number_in_decisions_x_and_y_is_checked_too(self):
        proc = self.lint_notes({"CLAUDE.md": "decisions 0005 and 0006\n"})
        numbered = [ln for ln in self.lines(proc, "warning:") if "by number" in ln]
        self.assertEqual(len(numbered), 1, proc.stdout)

    def test_files_under_ignored_directories_are_not_read(self):
        files = {
            f"{d}/CLAUDE.md": "acme-0007\n"
            for d in (".git/hooks", "node_modules/pkg", ".venv/lib", "venv/lib", "pkg/__pycache__")
        }
        proc = self.lint_notes(files)
        self.assertEqual(proc.returncode, 0, proc.stdout)
        self.assertFalse(self.has_line(proc, "error:", "refers to"), proc.stdout)

    def test_an_untracked_agents_md_is_read_from_the_working_tree(self):
        self.write("AGENTS.md", "acme-0007\n")
        self.assertEqual(git(self.acme, "ls-files", "AGENTS.md"), "")
        proc = self.cli("lint")
        self.assertTrue(self.has_line(proc, "error:", "AGENTS.md:1: refers to acme-0007"), proc.stdout)

    def test_an_unreadable_instruction_file_is_skipped_silently(self):
        path = self.write("CLAUDE.md", "acme-0007\n")
        path.chmod(0)
        try:
            if os.access(path, os.R_OK):
                self.skipTest("file permissions not enforced (root?)")
            proc = self.cli("lint")
        finally:
            path.chmod(0o644)
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertEqual(proc.stderr, "")

    def test_without_decision_roots_lint_does_not_read_instruction_files(self):
        (self.acme / ".claude" / "noemeo-guard.json").write_text("{}")
        before = self.cli("lint")
        self.write("CLAUDE.md", "acme-0007 and decision 0008\n")
        after = self.cli("lint")
        self.assertEqual((after.returncode, after.stdout), (before.returncode, before.stdout))
        self.assertNotIn("refers to", after.stdout)

    def test_lint_corpus_returns_instruction_file_findings_as_plain_strings(self):
        self.write("CLAUDE.md", "acme-0007\nacme-0011\ndecision 0016\n")
        errors, warnings = decisions.lint_corpus(load(self.acme), self.acme)
        self.assertIn("CLAUDE.md:1: refers to acme-0007, which is superseded; superseded by acme-0008", errors)
        self.assertIn("CLAUDE.md:2: refers to acme-0011, which is proposed, not accepted", warnings)
        self.assertTrue(any(w.startswith("CLAUDE.md:3:") and "by number" in w for w in warnings), warnings)

    def test_an_instruction_file_error_is_located_in_that_file(self):
        self.write("sub/AGENTS.md", "acme-0007\n")
        located, _warnings = decisions.lint_corpus_located(load(self.acme), self.acme)
        sources = [srcs for msg, srcs in located if "refers to acme-0007" in msg]
        self.assertEqual(len(sources), 1, located)
        self.assertEqual([Path(p).resolve() for p in sources[0]], [(self.acme / "sub" / "AGENTS.md").resolve()])


class Deps(CliCase):
    def test_deps_lists_dependents_and_amenders(self):
        self.write("docs/decisions/dep.md", record("acme-dep", depends_on=["acme-1"]))
        self.write("docs/decisions/other.md", record("acme-other", depends_on=["acme-3"]))
        proc = self.cli("deps", "acme-1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        # acme-2 amends and depends on acme-1; acme-dep depends on it
        self.assertEqual(sorted(proc.stdout.split()), ["acme-2", "acme-dep"])

    def test_a_decision_nothing_names_has_no_dependents(self):
        proc = self.cli("deps", "acme-2")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout.strip(), "")


class Show(CliCase):
    def test_show_returns_a_rejected_decision_labelled_rejected(self):
        self.write(
            "docs/decisions/rej.md",
            record("acme-rej", status="rejected", paths=["src/**"]),
        )
        proc = self.cli("show", "acme-rej")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        head = proc.stdout.strip().splitlines()[0]
        self.assertIn("acme-rej", head + proc.stdout)
        self.assertIn("rejected", head)
        self.assertIn("Do acme-rej.", proc.stdout)

    def test_show_labels_a_current_decision_with_its_status(self):
        proc = self.cli("show", "acme-1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("accepted", proc.stdout.strip().splitlines()[0])
        self.assertIn("Do acme-1.", proc.stdout)

    def test_show_unknown_id_exits_1(self):
        proc = self.cli("show", "acme-999")
        self.assertEqual(proc.returncode, 1)
        self.assertNotIn("Do acme-999", proc.stdout)


class ResolveCli(CliCase):
    def test_resolve_from_a_path_prints_id_version_source_and_text(self):
        d = next(d for d in load(self.acme).decisions if d.id == "acme-1")
        base = git(self.acme, "rev-parse", "HEAD")[:12]
        proc = self.cli("resolve", "--path", str(self.acme / "src" / "app.py"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"## acme-1  version {base}", proc.stdout)
        self.assertNotIn(d.content_hash, proc.stdout)  # the hash is not the version
        self.assertIn("docs/decisions/acme-1.md", proc.stdout)
        self.assertIn("Do acme-1.", proc.stdout)
        # the amendment follows its original
        self.assertIn("acme-2", proc.stdout)
        self.assertNotIn("acme-3", proc.stdout)

    def test_resolve_by_command_and_task(self):
        self.write("docs/decisions/design.md", record("acme-design", tasks=["design"]))
        proc = self.cli("resolve", "--command", "cd infra && terraform plan", "--task", "design")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("acme-3", proc.stdout)
        self.assertIn("acme-design", proc.stdout)
        self.assertNotIn("acme-1", proc.stdout)

    def test_resolve_from_a_diff_includes_untracked_files(self):
        self.write("docs/decisions/lib.md", record("acme-lib", paths=["lib/**"]))
        self.write("docs/decisions/other.md", record("acme-other", paths=["other/**"]))
        self.write("other/x.py", "x = 1\n")
        git(self.acme, "add", "-A")
        git(self.acme, "commit", "-q", "-m", "more")
        base = git(self.acme, "rev-parse", "HEAD")
        self.write("src/app.py", "print('changed')\n")
        git(self.acme, "add", "-A")
        git(self.acme, "commit", "-q", "-m", "change src")
        self.write("lib/new.py", "y = 2\n")  # untracked
        proc = self.cli("resolve", "--diff", base)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("acme-1", proc.stdout)  # src/app.py changed since base
        self.assertIn("acme-lib", proc.stdout)  # lib/new.py is untracked
        self.assertNotIn("acme-other", proc.stdout)  # other/x.py did not change

    def head(self):
        return git(self.acme, "rev-parse", "HEAD")[:12]

    def header(self, proc, id):
        return next(ln for ln in proc.stdout.splitlines() if ln.startswith(f"## {id}  "))

    def test_resolve_header_shows_the_commit_that_introduced_each_decision(self):
        base = self.head()
        self.write("docs/decisions/second.md", record("acme-second", paths=["src/**"]))
        git(self.acme, "add", "-A")
        git(self.acme, "commit", "-q", "-m", "second")
        second = self.head()
        self.assertNotEqual(base, second)
        proc = self.cli("resolve", "--path", str(self.acme / "src" / "app.py"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"## acme-1  version {base}", self.header(proc, "acme-1"))
        self.assertIn(f"## acme-second  version {second}", self.header(proc, "acme-second"))
        self.assertNotIn("uncommitted changes", proc.stdout)

    def test_resolve_marks_uncommitted_edits(self):
        base = self.head()
        self.write("docs/decisions/acme-1.md", record("acme-1", paths=["src/**"]) + "\nMore.\n")
        proc = self.cli("resolve", "--path", str(self.acme / "src" / "app.py"))
        self.assertIn(f"## acme-1  version {base}  (uncommitted changes)", proc.stdout)

    def test_resolve_marks_a_decision_that_was_never_committed(self):
        self.write("docs/decisions/new.md", record("acme-new", paths=["src/**"]))
        proc = self.cli("resolve", "--path", str(self.acme / "src" / "app.py"))
        self.assertIn("## acme-new  version none (not committed)", proc.stdout)
        self.assertNotIn("uncommitted changes", self.header(proc, "acme-new"))

    def test_dependency_label_keeps_its_place_next_to_the_version(self):
        proc = self.cli("resolve", "--path", str(self.acme / "src" / "app.py"))
        # acme-2 amends and depends on acme-1; acme-3 is out of scope
        self.assertIn(f"version {self.head()}", self.header(proc, "acme-2"))

    def test_commits_flag_is_gone(self):
        proc = self.cli("resolve", "--commits", "--path", str(self.acme / "src" / "app.py"))
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("--commits", proc.stderr)  # argparse: unrecognized arguments

    def test_resolve_never_prints_the_content_hash(self):
        proc = self.cli("resolve", "--path", str(self.acme / "src" / "app.py"))
        for d in load(self.acme).decisions:
            self.assertNotIn(d.content_hash, proc.stdout)

    def test_show_prints_the_version_line_in_the_same_wording(self):
        base = self.head()
        proc = self.cli("show", "acme-1")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn(f"version: {base}", proc.stdout.splitlines()[:4])
        self.write("docs/decisions/acme-1.md", record("acme-1", paths=["src/**"]) + "\nMore.\n")
        proc = self.cli("show", "acme-1")
        self.assertIn(f"version: {base}  (uncommitted changes)", proc.stdout)
        self.write("docs/decisions/new.md", record("acme-new"))
        proc = self.cli("show", "acme-new")
        self.assertIn("version: none (not committed)", proc.stdout)

    def test_index_shows_no_version_or_hash(self):
        proc = self.cli("index")
        self.assertNotIn("version", proc.stdout.lower())
        self.assertNotIn(self.head(), proc.stdout)
        for d in load(self.acme).decisions:
            self.assertNotIn(d.content_hash, proc.stdout)

    def test_lint_does_not_treat_uncommitted_decisions_as_errors(self):
        self.write("docs/decisions/new.md", record("acme-new"))
        self.write("docs/decisions/acme-1.md", record("acme-1", paths=["src/**"]) + "\nMore.\n")
        proc = self.cli("lint")
        self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
        self.assertNotIn("uncommitted", (proc.stdout + proc.stderr).lower())

    def branch_with_scopes(self):
        """main holds lib/ and other/ files with a decision each; feature is checked out."""
        self.write("docs/decisions/lib.md", record("acme-lib", paths=["lib/**"]))
        self.write("docs/decisions/other.md", record("acme-other", paths=["other/**"]))
        self.write("lib/x.py", "x = 1\n")
        self.write("other/x.py", "x = 1\n")
        git(self.acme, "add", "-A")
        git(self.acme, "commit", "-q", "-m", "scopes")
        git(self.acme, "branch", "-M", "main")
        git(self.acme, "checkout", "-q", "-b", "feature")

    def test_diff_includes_uncommitted_edits_to_tracked_files(self):
        self.write("src/app.py", "print('edited, not committed')\n")
        proc = self.cli("resolve", "--diff", "HEAD")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("acme-1", proc.stdout)

    def test_diff_covers_committed_and_uncommitted_changes_on_a_branch(self):
        self.branch_with_scopes()
        self.write("lib/x.py", "x = 2\n")
        git(self.acme, "add", "-A")
        git(self.acme, "commit", "-q", "-m", "change lib")
        self.write("other/x.py", "x = 3\n")  # tracked, uncommitted
        proc = self.cli("resolve", "--diff", "main")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("acme-lib", proc.stdout)
        self.assertIn("acme-other", proc.stdout)
        self.assertNotIn("acme-1", proc.stdout)  # src/app.py is unchanged

    def test_diff_with_nothing_changed_resolves_nothing(self):
        self.branch_with_scopes()
        proc = self.cli("resolve", "--diff", "main")
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertNotIn("acme-", proc.stdout)

    def test_diff_finds_untracked_files_when_the_project_is_a_subdirectory(self):
        sub = self.acme / "sub"
        (sub / ".claude").mkdir(parents=True)
        (sub / ".claude" / "noemeo-guard.json").write_text(
            json.dumps({"decision_roots": ["docs/decisions"]})
        )
        self.write("sub/docs/decisions/sd.md", record("acme-sub", paths=["sub/src/**"]))
        self.write("sub/src/old.py", "a = 1\n")
        git(self.acme, "add", "-A")
        git(self.acme, "commit", "-q", "-m", "sub")
        self.write("sub/src/new.py", "b = 2\n")  # untracked, under the subdirectory
        proc = self.cli("resolve", "--diff", "HEAD", env_project=sub)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("acme-sub", proc.stdout)

    def test_resolve_includes_the_depends_on_closure_of_decisions_in_scope(self):
        self.write("docs/decisions/b1.md", record("b-1", paths=["src/**"], depends_on=["a-1", "d-1"]))
        self.write("docs/decisions/a1.md", record("a-1", depends_on=["z-1"]))
        self.write("docs/decisions/z1.md", record("z-1"))
        self.write("docs/decisions/c1.md", record("c-1"))
        self.write("docs/decisions/d1.md", record("d-1", status="superseded"))
        proc = self.cli("resolve", "--path", str(self.acme / "src" / "x.py"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        for text in ("Do b-1.", "Do a-1.", "Do z-1."):  # in scope, dependency, transitive
            self.assertIn(text, proc.stdout)
        self.assertNotIn("Do c-1.", proc.stdout)  # unrelated, not in scope
        self.assertNotIn("Do d-1.", proc.stdout)  # superseded: not current


if __name__ == "__main__":
    unittest.main()
