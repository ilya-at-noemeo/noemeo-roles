"""The decisions docs and skills exist, say what they must, and their
examples are real.

Run: /usr/local/bin/python3 -m unittest tests.test_decisions_docs

Extraction convention for docs/decisions.md: the examples are the first
fenced code block (``` ... ```, any info string, no nested fences) after
a heading whose text contains "Example: record" and the first fenced
block after a heading whose text contains "Example: section". The record
example is written as a file; the section example likewise. Each must be
self-contained: every id it names in depends_on, supersedes or amends
must be defined by the other example or by itself.
"""

import json
import re
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"
CLI = HOOKS / "decisions.py"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HOOKS))
from decisions_format import parse_file  # noqa: E402

DOC = ROOT / "docs" / "decisions.md"
DECISIONS_SKILL = ROOT / "skills" / "noemeo-decisions" / "SKILL.md"
REVIEW_SKILL = ROOT / "skills" / "noemeo-design-review" / "SKILL.md"
AGREEMENT = ROOT / "roles" / "working-agreement.md"
NEW_OR_CHANGED = [DOC, DECISIONS_SKILL, REVIEW_SKILL, AGREEMENT]
# Names of Noemeo products; the repo is public and generic (foundation 0004).
PRODUCT_NAMES = ("photo", "legal", "lightroom")


def fenced_example(text: str, heading_contains: str) -> str | None:
    """The first fenced block after a heading containing `heading_contains`."""
    lines = text.splitlines()
    for i, line in enumerate(lines):
        if line.lstrip().startswith("#") and heading_contains in line:
            block: list[str] | None = None
            for later in lines[i + 1 :]:
                if later.startswith("```"):
                    if block is None:
                        block = []
                        continue
                    return "\n".join(block) + "\n"
                if block is not None:
                    block.append(later)
            return None
    return None


def front_matter(path: Path) -> dict:
    text = path.read_text()
    m = re.match(r"---\n(.*?)\n---\n", text, re.S)
    assert m, f"{path} has no front matter"
    fields = {}
    for line in m.group(1).splitlines():
        key, _, value = line.partition(":")
        fields[key.strip()] = value.strip()
    return fields


def git(repo: Path, *args: str) -> None:
    subprocess.run(
        ["git", "-C", str(repo), "-c", "user.email=t@t", "-c", "user.name=t", *args],
        check=True,
        capture_output=True,
    )


class FormatDocTest(unittest.TestCase):
    def test_example_in_docs_parses_and_lints_clean(self) -> None:
        self.assertTrue(DOC.is_file(), "docs/decisions.md is missing")
        text = DOC.read_text()
        record = fenced_example(text, "Example: record")
        section = fenced_example(text, "Example: section")
        self.assertIsNotNone(record, 'no fenced block under a heading "Example: record"')
        self.assertIsNotNone(section, 'no fenced block under a heading "Example: section"')
        self.assertTrue(record.startswith("---\n"), "the record example starts with front matter")
        self.assertIn("<!-- decision", section)

        with tempfile.TemporaryDirectory() as tmp:
            acme = Path(tmp).resolve() / "acme"
            (acme / "docs" / "decisions").mkdir(parents=True)
            (acme / ".claude").mkdir()
            (acme / ".claude" / "noemeo-guard.json").write_text(
                json.dumps({"decision_roots": ["docs/decisions"]})
            )
            files = {
                "record.md": record,
                "section.md": section,
            }
            for name, body in files.items():
                (acme / "docs" / "decisions" / name).write_text(body)
            git(acme, "init", "-q")
            git(acme, "add", "-A")
            git(acme, "commit", "-q", "-m", "examples")

            for name in files:
                with self.subTest(example=name):
                    found, errors = parse_file(acme / "docs" / "decisions" / name)
                    self.assertEqual([], [e.message for e in errors])
                    self.assertEqual(1, len(found), f"{name} should hold exactly one decision")

            result = subprocess.run(
                [sys.executable, str(CLI), "lint", "--project", str(acme)],
                capture_output=True,
                text=True,
            )
            self.assertEqual(0, result.returncode, result.stdout + result.stderr)

    def test_format_doc_covers_the_reference_topics(self) -> None:
        self.assertTrue(DOC.is_file(), "docs/decisions.md is missing")
        text = DOC.read_text()
        for term in (
            "decision_roots",
            "paths",
            "repo",
            "commands",
            "tasks",
            "always",
            "proposed",
            "accepted",
            "temporary",
            "superseded",
            "retired",
            "rejected",
            "depends_on",
            "supersedes",
            "amends",
            "deliver",
        ):
            with self.subTest(term=term):
                self.assertIn(term, text)
        self.assertRegex(text, r"(?i)folders? (never|do(es)? not|don't) set scope")


class SkillsTest(unittest.TestCase):
    def test_decisions_skill_exists_and_names_the_cli(self) -> None:
        self.assertTrue(DECISIONS_SKILL.is_file(), "skills/noemeo-decisions/SKILL.md is missing")
        fields = front_matter(DECISIONS_SKILL)
        self.assertEqual("noemeo-decisions", fields.get("name"))
        self.assertTrue(fields.get("description"), "the skill needs a description")
        body = DECISIONS_SKILL.read_text()
        for command in ("resolve", "deps", "lint"):
            with self.subTest(command=command):
                self.assertRegex(body, rf"decisions\.py {command}\b|`{command}`")
        self.assertIn("proposed", body)
        self.assertRegex(
            body,
            r"(?is)(only (a|the) (person|owner)[^.]*accepted|accepted[^.]*only (a|the) (person|owner))",
        )
        for trigger in ("record a decision", "supersede", "amend"):
            with self.subTest(trigger=trigger):
                self.assertIn(trigger, fields["description"].lower())

    def test_design_review_resolves_decisions_from_the_diff(self) -> None:
        body = REVIEW_SKILL.read_text()
        self.assertIn("decision_roots", body)
        self.assertIn("resolve --diff", body)
        self.assertIn("--commits", body)
        self.assertRegex(body, r"(?i)versions?")

    def test_working_agreement_sends_settled_knowledge_to_decision_roots(self) -> None:
        text = AGREEMENT.read_text()
        self.assertIn("decision roots", text)
        self.assertIn("noemeo-decisions", text)
        self.assertRegex(text, r"(?i)private memory")
        self.assertRegex(text, r"(?i)only a person accepts")


class GenericRepoTest(unittest.TestCase):
    def test_no_product_names_in_new_files(self) -> None:
        for path in NEW_OR_CHANGED:
            with self.subTest(file=path.relative_to(ROOT).as_posix()):
                self.assertTrue(path.is_file(), f"{path.name} is missing")
                text = path.read_text().lower()
                for name in PRODUCT_NAMES:
                    self.assertNotIn(name, text, f"{path.name} names a product: {name}")


if __name__ == "__main__":
    unittest.main()
