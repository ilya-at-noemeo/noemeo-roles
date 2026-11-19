"""Parsing decisions from Markdown: front matter on a decision record,
`<!-- decision ... -->` markers under section headings.

Run: /usr/local/bin/python3 -m unittest tests.test_decisions_format

Every file is written to a temp directory; names are invented.
"""

import dataclasses
import sys
import tempfile
import unittest
from pathlib import Path

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HOOKS))
import decisions_format  # noqa: E402
from decisions_format import (  # noqa: E402
    CURRENT,
    KINDS,
    STATUSES,
    Decision,
    FormatError,
    parse_file,
    title_of,
)

RECORD = """\
---
id: acme-0001
kind: policy
status: accepted
binding: true
summary: "Use the acme profile"
commands: [aws *, terraform *]
---
# 0001: Use the acme profile

## Decision
Widgets are deployed with the acme profile.

## Why
Because the widget account is separate.

## How to apply
Always --profile acme.

## Review checks
- Is the profile named?
"""

MARKER = """\
# Architecture

## Boundaries
<!-- decision
id: arch-boundary
kind: architecture
status: accepted
binding: false
summary: s
paths: [src/**]
-->
body
### sub
more
## Next
not included
"""


def only(result):
    decisions, errors = result
    assert errors == [], errors
    assert len(decisions) == 1, decisions
    return decisions[0]


class TempCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def write(self, name, content):
        p = self.root / name
        p.write_bytes(content.encode("utf-8"))
        return p


class Constants(unittest.TestCase):
    def test_vocabulary(self):
        self.assertEqual(KINDS, ("policy", "architecture", "product", "finding"))
        self.assertEqual(
            STATUSES,
            ("proposed", "accepted", "temporary", "superseded", "retired", "rejected", "open"),
        )
        self.assertEqual(CURRENT, ("accepted", "temporary"))


class ParseRecord(TempCase):
    def test_front_matter_record(self):
        p = self.write("0001-acme.md", RECORD)
        d = only(parse_file(p))
        self.assertIsInstance(d, Decision)
        self.assertEqual(d.id, "acme-0001")
        self.assertEqual(d.kind, "policy")
        self.assertEqual(d.status, "accepted")
        self.assertEqual(d.summary, "Use the acme profile")
        self.assertEqual(d.commands, ("aws *", "terraform *"))
        self.assertTrue(d.binding)
        self.assertEqual(d.paths, ())
        self.assertIsNone(d.repo)
        self.assertFalse(d.always)
        self.assertIsNone(d.heading)
        self.assertEqual(d.source, p)
        self.assertIn("Always --profile acme.", d.text)
        self.assertIn("Review checks", d.text)
        self.assertIn("Is the profile named?", d.text)
        self.assertNotIn("## Decision", d.text)
        self.assertNotIn("Widgets are deployed", d.text)
        self.assertNotIn("Because the widget account", d.text)
        self.assertEqual(len(d.content_hash), 12)
        int(d.content_hash, 16)  # hex

    def test_decision_is_frozen(self):
        d = only(parse_file(self.write("0001-acme.md", RECORD)))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            d.id = "other"

    def test_scope_and_relation_fields(self):
        text = RECORD.replace(
            "commands: [aws *, terraform *]\n",
            "repo: \"*\"\npaths: [src/**, docs/*.md]\ntasks: [design, review]\n"
            "always: true\ndepends_on: [acme-0000]\nsupersedes: [acme-0000a]\n"
            "amends: [acme-0000b]\norigin: owner\nevidence: [a.md, b.md]\n",
        )
        d = only(parse_file(self.write("0001-acme.md", text)))
        self.assertEqual(d.repo, "*")
        self.assertEqual(d.paths, ("src/**", "docs/*.md"))
        self.assertEqual(d.tasks, ("design", "review"))
        self.assertTrue(d.always)
        self.assertEqual(d.depends_on, ("acme-0000",))
        self.assertEqual(d.supersedes, ("acme-0000a",))
        self.assertEqual(d.amends, ("acme-0000b",))
        self.assertEqual(d.origin, "owner")
        self.assertEqual(d.evidence, ("a.md", "b.md"))

    def test_binding_false_and_comment_lines(self):
        text = RECORD.replace("binding: true", "# a comment\nbinding: false")
        d = only(parse_file(self.write("0001-acme.md", text)))
        self.assertFalse(d.binding)

    def test_deliver_all_and_named_headings(self):
        all_text = RECORD.replace("binding: true", "binding: true\ndeliver: all")
        d = only(parse_file(self.write("all.md", all_text)))
        self.assertIn("Widgets are deployed", d.text)
        self.assertIn("Because the widget account", d.text)
        self.assertIn("Always --profile acme.", d.text)
        self.assertIn("Is the profile named?", d.text)

        named = RECORD.replace("binding: true", "binding: true\ndeliver: [Decision]")
        d = only(parse_file(self.write("named.md", named)))
        self.assertIn("Widgets are deployed", d.text)
        self.assertNotIn("Always --profile acme.", d.text)
        self.assertNotIn("Is the profile named?", d.text)
        self.assertNotIn("Because the widget account", d.text)

    def test_quoted_list_items_keep_commas(self):
        text = RECORD.replace("commands: [aws *, terraform *]", 'tasks: ["a, b", c]')
        d = only(parse_file(self.write("q.md", text)))
        self.assertEqual(d.tasks, ("a, b", "c"))

    def test_inline_lists_strip_blanks_around_unquoted_items(self):
        base = "---\nid: acme-9\nkind: policy\nstatus: accepted\nbinding: true\nsummary: s\n"
        p = self.write("lists.md", base + "tasks: [design, review]\n"
                       "commands: [aws *,  terraform *]\n---\n# T\n")
        d = only(parse_file(p))
        self.assertEqual(d.tasks, ("design", "review"))
        self.assertEqual(d.commands, ("aws *", "terraform *"))
        p = self.write("quoted.md", base + 'tasks: ["a, b", c]\n---\n# T\n')
        self.assertEqual(only(parse_file(p)).tasks, ("a, b", "c"))

    def test_blanks_around_quoted_list_items_are_dropped_inside_quotes_kept(self):
        base = "---\nid: acme-9\nkind: policy\nstatus: accepted\nbinding: true\nsummary: s\n"
        p = self.write("q1.md", base + 'tasks: ["design", "review"]\n'
                       'paths: [ "x/**" ,  "y/**"]\n---\n# T\n')
        d = only(parse_file(p))
        self.assertEqual(d.tasks, ("design", "review"))
        self.assertEqual(d.paths, ("x/**", "y/**"))
        p = self.write("q2.md", base + 'tasks: ["a b", c]\n---\n# T\n')
        self.assertEqual(only(parse_file(p)).tasks, ("a b", "c"))

    def test_title_of(self):
        p = self.write("0001-acme.md", RECORD)
        self.assertEqual(title_of(p), "0001: Use the acme profile")
        q = self.write("no-title.md", "just text\n")
        self.assertEqual(title_of(q), "no-title.md")


class ParseMarker(TempCase):
    def test_section_marker_takes_body_to_next_same_or_higher_heading(self):
        p = self.write("arch.md", MARKER)
        d = only(parse_file(p))
        self.assertEqual(d.heading, "Boundaries")
        self.assertEqual(d.id, "arch-boundary")
        self.assertEqual(d.kind, "architecture")
        self.assertFalse(d.binding)
        self.assertEqual(d.paths, ("src/**",))
        self.assertEqual(d.source, p)
        self.assertIn("body", d.text)
        self.assertIn("more", d.text)
        self.assertNotIn("not included", d.text)
        self.assertNotIn("kind: architecture", d.text)  # marker not delivered
        self.assertEqual(len(d.content_hash), 12)

    def test_comment_line_inside_marker_is_not_a_heading(self):
        text = MARKER.replace("binding: false\n", "binding: false\n# a comment line\n")
        decisions, errors = parse_file(self.write("arch.md", text))
        self.assertEqual(errors, [])
        d = decisions[0]
        self.assertEqual(d.heading, "Boundaries")
        self.assertIn("body", d.text)
        self.assertIn("more", d.text)
        self.assertNotIn("not included", d.text)

    def test_two_markers_in_one_file(self):
        text = MARKER.replace(
            "## Next\nnot included\n",
            "## Next\n<!-- decision\nid: arch-next\nkind: architecture\n"
            "status: accepted\nbinding: true\nsummary: second\n-->\nsecond body\n",
        )
        decisions, errors = parse_file(self.write("arch.md", text))
        self.assertEqual(errors, [])
        self.assertEqual([d.id for d in decisions], ["arch-boundary", "arch-next"])
        self.assertEqual([d.heading for d in decisions], ["Boundaries", "Next"])
        self.assertIn("second body", decisions[1].text)
        self.assertNotIn("second body", decisions[0].text)
        self.assertNotIn("more", decisions[1].text)


class Errors(TempCase):
    def test_unknown_kind_and_status_are_errors(self):
        text = RECORD.replace("kind: policy", "kind: widget").replace(
            "status: accepted", "status: maybe"
        )
        p = self.write("bad.md", text)
        decisions, errors = parse_file(p)
        self.assertEqual(decisions, [])
        self.assertEqual(len(errors), 2)
        for e in errors:
            self.assertIsInstance(e, FormatError)
            self.assertEqual(e.path, p)
            self.assertGreaterEqual(e.line, 1)
        messages = " ".join(e.message for e in errors)
        self.assertIn("kind", messages)
        self.assertIn("status", messages)

    def test_missing_required_field_is_an_error(self):
        for field in ("kind", "status", "binding", "summary"):
            with self.subTest(field=field):
                lines = [
                    ln for ln in RECORD.split("\n") if not ln.startswith(field + ":")
                ]
                p = self.write(f"missing-{field}.md", "\n".join(lines))
                decisions, errors = parse_file(p)
                self.assertEqual(decisions, [])
                self.assertEqual(len(errors), 1)
                self.assertIn(field, errors[0].message)
                self.assertEqual(errors[0].path, p)

    def test_front_matter_without_id_is_not_a_decision(self):
        text = "---\nname: widget-guide\ndescription: How to use widgets\n---\n# Widgets\n\n## How to apply\nText.\n"
        self.assertEqual(parse_file(self.write("guide.md", text)), ([], []))
        no_id = "\n".join(ln for ln in RECORD.split("\n") if not ln.startswith("id:"))
        self.assertEqual(parse_file(self.write("no-id.md", no_id)), ([], []))

    def test_unknown_key_is_an_error(self):
        text = RECORD.replace("binding: true", "binding: true\npaht: [src/**]")
        decisions, errors = parse_file(self.write("typo.md", text))
        self.assertEqual(decisions, [])
        self.assertEqual(len(errors), 1)
        self.assertIn("paht", errors[0].message)

    def test_marker_errors_do_not_drop_other_markers(self):
        text = MARKER.replace(
            "## Next\nnot included\n",
            "## Next\n<!-- decision\nid: arch-next\nkind: nonsense\n"
            "status: accepted\nbinding: true\nsummary: second\n-->\nsecond body\n",
        )
        decisions, errors = parse_file(self.write("arch.md", text))
        self.assertEqual([d.id for d in decisions], ["arch-boundary"])
        self.assertEqual(len(errors), 1)
        self.assertIn("kind", errors[0].message)

    def test_unterminated_front_matter_is_an_error_not_a_crash(self):
        text = RECORD.replace("---\n# 0001", "# 0001", 1)
        p = self.write("open.md", text)
        decisions, errors = parse_file(p)
        self.assertEqual(decisions, [])
        self.assertGreaterEqual(len(errors), 1)
        self.assertEqual(errors[0].path, p)
        self.assertEqual(errors[0].line, 1)

    def test_unterminated_marker_is_an_error_not_a_crash(self):
        text = MARKER.replace("-->\n", "")
        decisions, errors = parse_file(self.write("open-marker.md", text))
        self.assertEqual(decisions, [])
        self.assertGreaterEqual(len(errors), 1)

    def test_crlf_and_bom_parse_like_lf(self):
        lf = self.root / "lf.md"
        lf.write_bytes(RECORD.encode("utf-8"))
        crlf = self.root / "crlf.md"
        crlf.write_bytes(RECORD.replace("\n", "\r\n").encode("utf-8"))
        bom = self.root / "bom.md"
        bom.write_bytes(b"\xef\xbb\xbf" + RECORD.encode("utf-8"))
        both = self.root / "both.md"
        both.write_bytes(b"\xef\xbb\xbf" + RECORD.replace("\n", "\r\n").encode("utf-8"))
        base = only(parse_file(lf))
        for p in (crlf, bom, both):
            with self.subTest(file=p.name):
                d = only(parse_file(p))
                self.assertEqual(dataclasses.replace(d, source=lf), base)
                self.assertNotIn("\r", d.text)

    def test_crlf_marker_parses_like_lf(self):
        lf = self.root / "lf.md"
        lf.write_bytes(MARKER.encode("utf-8"))
        crlf = self.root / "crlf.md"
        crlf.write_bytes(MARKER.replace("\n", "\r\n").encode("utf-8"))
        self.assertEqual(
            dataclasses.replace(only(parse_file(crlf)), source=lf), only(parse_file(lf))
        )

    def test_file_without_front_matter_or_markers_gives_nothing(self):
        p = self.write("plain.md", "# Notes\n\nNothing to see.\n")
        self.assertEqual(parse_file(p), ([], []))


class ParseText(TempCase):
    def test_parse_text_matches_parse_file(self):
        for name, text in (("r.md", RECORD), ("m.md", MARKER)):
            with self.subTest(name=name):
                p = self.write(name, text)
                self.assertEqual(decisions_format.parse_text(text, p), parse_file(p))

    def test_parse_text_reads_no_file(self):
        missing = self.root / "never-written.md"
        decisions, errors = decisions_format.parse_text(RECORD, missing)
        self.assertEqual(errors, [])
        self.assertEqual(decisions[0].id, "acme-0001")
        self.assertEqual(decisions[0].source, missing)


class ContentHash(TempCase):
    def version(self, text, name="v.md"):
        return only(parse_file(self.write(name, text))).content_hash

    def test_content_hash_changes_with_text_or_fields_only(self):
        base = self.version(RECORD)
        self.assertEqual(self.version(RECORD, "again.md"), base)  # stable, path-independent

        edited_text = RECORD.replace("Always --profile acme.", "Always --profile widget.")
        self.assertNotEqual(self.version(edited_text), base)

        edited_summary = RECORD.replace("Use the acme profile\"", "Use the widget profile\"")
        self.assertNotEqual(self.version(edited_summary), base)

        edited_field = RECORD.replace("[aws *, terraform *]", "[aws *]")
        self.assertNotEqual(self.version(edited_field), base)

        # "## Why" is not delivered: editing it leaves the version alone
        edited_why = RECORD.replace("separate.", "separate, and audited.")
        self.assertNotEqual(edited_why, RECORD)
        self.assertEqual(self.version(edited_why), base)

        # so does the title line outside the delivered sections
        edited_title = RECORD.replace("# 0001: Use", "# 0001: Prefer")
        self.assertEqual(self.version(edited_title), base)


if __name__ == "__main__":
    unittest.main()
