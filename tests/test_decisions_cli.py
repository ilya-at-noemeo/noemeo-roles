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
        proc = self.cli("resolve", "--path", str(self.acme / "src" / "app.py"))
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertIn("acme-1", proc.stdout)
        self.assertIn(d.version, proc.stdout)
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

    def test_commits_flag_adds_the_last_commit_of_each_source(self):
        self.write("docs/decisions/first.md", record("acme-first", paths=["src/**"]))
        git(self.acme, "add", "-A")
        git(self.acme, "commit", "-q", "-m", "first")
        first = git(self.acme, "rev-parse", "HEAD")
        self.write("docs/decisions/second.md", record("acme-second", paths=["src/**"]))
        git(self.acme, "add", "-A")
        git(self.acme, "commit", "-q", "-m", "second")
        second = git(self.acme, "rev-parse", "HEAD")
        self.assertNotEqual(first, second)
        path = str(self.acme / "src" / "app.py")

        plain = self.cli("resolve", "--path", path)
        self.assertNotIn(first[:7], plain.stdout)
        self.assertNotIn(second[:7], plain.stdout)

        proc = self.cli("resolve", "--commits", "--path", path)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        by_id = {}
        current = None
        for ln in proc.stdout.splitlines():
            for id in ("acme-first", "acme-second"):
                if id in ln:
                    current = id
            if current:
                by_id.setdefault(current, []).append(ln)
        self.assertIn(first[:7], "\n".join(by_id["acme-first"]))
        self.assertIn(second[:7], "\n".join(by_id["acme-second"]))
        self.assertNotIn(second[:7], "\n".join(by_id["acme-first"]))


if __name__ == "__main__":
    unittest.main()
