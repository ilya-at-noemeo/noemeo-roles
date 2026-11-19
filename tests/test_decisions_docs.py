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
        self.assertNotIn("--commits", body)  # resolve prints the version itself
        self.assertRegex(body, r"(?i)versions?")

    def test_working_agreement_sends_settled_knowledge_to_decision_roots(self) -> None:
        text = AGREEMENT.read_text()
        self.assertIn("decision roots", text)
        self.assertIn("noemeo-decisions", text)
        self.assertRegex(text, r"(?i)private memory")
        self.assertRegex(text, r"(?i)only a person accepts")


class FollowUpDocs(unittest.TestCase):
    def test_no_doc_skill_or_hook_still_mentions_the_commits_flag(self) -> None:
        for path in [*ROOT.glob("docs/*.md"), *ROOT.glob("skills/*/SKILL.md"),
                     *HOOKS.glob("*.py"), ROOT / "README.md"]:
            with self.subTest(path=path.name):
                text = path.read_text()
                self.assertNotIn("--commits", text)
                self.assertNotIn("_last_commit", text)

    def test_decisions_doc_defines_version_as_the_git_commit(self) -> None:
        text = DOC.read_text()
        self.assertRegex(text, r"(?i)version[^.\n]*(git )?commit")
        self.assertRegex(text, r"(?i)content hash")
        self.assertIn("uncommitted changes", text)
        self.assertRegex(text, r"(?i)renames? (are )?not followed|not follow")

    def test_subagents_get_the_index_now(self) -> None:
        text = DOC.read_text()
        self.assertNotRegex(text, r"(?i)subagents? get no index")
        self.assertIn("subagent-start", text + (ROOT / "docs" / "hooks.md").read_text())
        self.assertIn("SubagentStart", (ROOT / "docs" / "hooks.md").read_text())

    def test_codex_doc_records_the_missing_subagent_start_as_a_gap(self) -> None:
        text = (ROOT / "docs" / "codex.md").read_text()
        gaps = text[text.index("Gaps:"):]
        self.assertRegex(gaps, r"(?i)subagent-?start|subagent[^.]*index")

    def test_python_floor_is_documented(self) -> None:
        for path in (ROOT / "docs" / "hooks.md", ROOT / "README.md"):
            with self.subTest(path=path.name):
                text = path.read_text()
                self.assertRegex(text, r"3\.12")
                self.assertIn("python3 --version", text)
        hooks = (ROOT / "docs" / "hooks.md").read_text()
        self.assertIn("/usr/bin/python3", hooks)
        self.assertRegex(hooks, r"(?i)3\.9")

    def test_plugin_version_is_0_25_0(self) -> None:
        manifest = json.loads((ROOT / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(manifest["version"], "0.25.0")


class InstructionFileDocs(unittest.TestCase):
    def section(self) -> str:
        text = DOC.read_text()
        m = re.search(r"^#+ .*CLAUDE\.md and AGENTS\.md.*$", text, re.M)
        self.assertIsNotNone(m, "docs/decisions.md has no 'CLAUDE.md and AGENTS.md' section")
        rest = text[m.end():]
        nxt = re.search(r"^#{1,%d} " % len(m.group(0).split()[0]), rest, re.M)
        return rest[: nxt.start()] if nxt else rest

    def test_decisions_doc_explains_one_home_per_rule(self) -> None:
        body = self.section()
        self.assertRegex(body, r"(?i)one home per rule")
        self.assertRegex(body, r"(?i)override|precedence|wins")
        self.assertRegex(body, r"(?i)orientation")
        self.assertRegex(body, r"(?i)restate")
        self.assertRegex(body, r"(?i)review")

    def test_decisions_doc_lists_the_instruction_file_lint_checks(self) -> None:
        body = self.section()
        for status in ("superseded", "retired", "rejected", "proposed", "open"):
            with self.subTest(status=status):
                self.assertIn(status, body)
        self.assertRegex(body, r"(?i)by number|numbered")
        self.assertRegex(body, r"(?i)error")
        self.assertRegex(body, r"(?i)warning")

    def test_both_skills_mention_instruction_files(self) -> None:
        for path in (REVIEW_SKILL, DECISIONS_SKILL):
            with self.subTest(skill=path.parent.name):
                text = path.read_text()
                self.assertIn("CLAUDE.md", text)
                self.assertIn("AGENTS.md", text)
        self.assertRegex(REVIEW_SKILL.read_text(), r"(?i)restate")
        decisions_text = DECISIONS_SKILL.read_text()
        self.assertRegex(decisions_text, r"(?i)reference[^.]*\bid\b|\bid\b[^.]*reference")
        self.assertRegex(decisions_text, r"(?is)AGENTS\.md[^.]*(owner|Codex)")


if __name__ == "__main__":
    unittest.main()
