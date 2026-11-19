"""Delivering decisions on tool calls: binding decisions deny the first
matching action once (PreToolUse), every decision in scope arrives as
feedback after a read or edit (PostToolUse), state per context in the
Git dir.

Run: /usr/local/bin/python3 -m unittest tests.test_decision_delivery

Runs hooks/decision_delivery.py as Claude Code does (JSON on stdin,
CLAUDE_PROJECT_DIR set) against a throwaway `git init` project. Names are
invented. No network.
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOOK = ROOT / "hooks" / "decision_delivery.py"
HOOKS_JSON = ROOT / "hooks" / "hooks.json"
STATE = "noemeo-decisions-delivered.json"
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "hooks"))
from decisions import load  # noqa: E402


def _value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(f'"{x}"' for x in v) + "]"
    return str(v)


class Project(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name) / "acme"
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        self.config(["docs/decisions"])

    def config(self, roots):
        (self.project / ".claude").mkdir(exist_ok=True)
        (self.project / ".claude" / "noemeo-guard.json").write_text(
            json.dumps({"decision_roots": roots})
        )

    def decision(self, id, text=None, *, binding=True, rel=None, **extra):
        path = self.project / (rel or f"docs/decisions/{id}.md")
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = {
            "id": id,
            "kind": "policy",
            "status": "accepted",
            "binding": binding,
            "summary": f"Summary of {id}",
        }
        fields.update(extra)
        front = "\n".join(f"{k}: {_value(v)}" for k, v in fields.items())
        body = text if text is not None else f"Do {id}."
        path.write_text(f"---\n{front}\n---\n# Record {id}\n\n## How to apply\n{body}\n")
        return path

    def run_hook(self, event):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        done = subprocess.run(
            [sys.executable, str(HOOK)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.project),
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        return json.loads(done.stdout) if done.stdout.strip() else None

    def event(self, name, tool, target, session="s1", agent=None):
        key = "command" if tool == "Bash" else (
            "notebook_path" if tool == "NotebookEdit" else "file_path"
        )
        if key != "command":
            target = str(self.project / target)
        e = {
            "hook_event_name": name,
            "session_id": session,
            "tool_name": tool,
            "tool_input": {key: target},
            "cwd": str(self.project),
        }
        if agent:
            e["agent_id"] = agent
        return e

    def pre(self, tool, target, **kw):
        return self.run_hook(self.event("PreToolUse", tool, target, **kw))

    def post(self, tool, target, **kw):
        return self.run_hook(self.event("PostToolUse", tool, target, **kw))

    def state(self):
        return json.loads((self.project / ".git" / STATE).read_text())


def verdict(out):
    if not out:
        return None
    return out.get("hookSpecificOutput", {}).get("permissionDecision")


def reason(out):
    return out["hookSpecificOutput"]["permissionDecisionReason"]


class Binding(Project):
    def setUp(self):
        super().setUp()
        self.path = self.decision(
            "acme-0001", "Always --profile acme.", paths=["src/**"], commands=["aws *"]
        )

    def test_first_edit_in_scope_is_denied_once_with_the_text(self):
        out = self.pre("Edit", "src/a.py")
        self.assertEqual(verdict(out), "deny")
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "PreToolUse")
        self.assertIn("acme-0001", reason(out))
        self.assertIn("Always --profile acme.", reason(out))
        self.assertIn("Delivered once", reason(out))
        self.assertIsNone(verdict(self.pre("Edit", "src/a.py")))  # retry passes

    def test_every_edit_tool_is_covered_and_delivery_is_shared(self):
        self.assertEqual(verdict(self.pre("NotebookEdit", "src/n.ipynb")), "deny")
        self.assertIsNone(verdict(self.pre("Write", "src/b.py")))  # already delivered

    def test_edit_outside_scope_is_never_denied(self):
        self.assertIsNone(self.pre("Edit", "docs/readme.md"))
        self.assertIsNone(self.pre("Write", "/tmp/elsewhere/a.py"))

    def test_command_in_scope_is_denied_once(self):
        out = self.pre("Bash", "AWS_PROFILE=x aws s3 ls")
        self.assertEqual(verdict(out), "deny")
        self.assertIn("Always --profile acme.", reason(out))
        self.assertIsNone(verdict(self.pre("Bash", "aws s3 ls")))

    def test_command_out_of_scope_is_not_denied(self):
        self.assertIsNone(self.pre("Bash", "ls -la"))

    def test_changed_version_is_delivered_again(self):
        self.assertEqual(verdict(self.pre("Edit", "src/a.py")), "deny")
        self.assertIsNone(verdict(self.pre("Edit", "src/a.py")))
        self.decision("acme-0001", "Now use --profile widget.", paths=["src/**"])
        out = self.pre("Edit", "src/a.py")
        self.assertEqual(verdict(out), "deny")
        self.assertIn("Now use --profile widget.", reason(out))
        self.assertIsNone(verdict(self.pre("Edit", "src/a.py")))

    def test_read_never_blocks_but_delivers_binding_after_and_prevents_later_deny(self):
        self.assertIsNone(self.pre("Read", "src/a.py"))  # no pre-read delivery
        out = self.post("Read", "src/a.py")
        self.assertEqual(out["decision"], "block")  # feedback, the read already happened
        self.assertIn("acme-0001", out["reason"])
        self.assertIn("Always --profile acme.", out["reason"])
        self.assertIsNone(verdict(self.pre("Edit", "src/a.py")))  # counted as delivered

    def test_amendment_is_delivered_with_its_original(self):
        self.decision("acme-0002", "Also pass --region ca.", amends=["acme-0001"])
        out = self.pre("Edit", "src/a.py")
        self.assertEqual(verdict(out), "deny")
        self.assertIn("Always --profile acme.", reason(out))
        self.assertIn("Amended by acme-0002:", reason(out))
        self.assertIn("Also pass --region ca.", reason(out))

    def test_depends_on_is_not_delivered(self):
        self.decision("acme-0003", "DEPENDENCY-TEXT-77")
        self.decision("acme-0001", "Always --profile acme.", paths=["src/**"],
                      depends_on=["acme-0003"])
        out = self.pre("Edit", "src/a.py")
        self.assertEqual(verdict(out), "deny")
        self.assertNotIn("DEPENDENCY-TEXT-77", reason(out))
        self.assertNotIn("acme-0003", reason(out))

    def test_delivery_carries_no_metadata(self):
        self.decision(
            "acme-0001", "Always --profile acme.", paths=["src/**"],
            origin="owner-chat-2026", evidence=["measured-in-study-7"],
            summary="A summary line",
        )
        version = next(d.content_hash for d in load(self.project).decisions
                       if d.id == "acme-0001")
        out = self.pre("Edit", "src/a.py")
        text = reason(out)
        self.assertIn("acme-0001", text)
        self.assertIn("Always --profile acme.", text)
        for hidden in (version, "owner-chat-2026", "measured-in-study-7",
                       "policy", "binding", "kind", "origin", "evidence",
                       "version", "paths", "src/**", "scope", "depends_on",
                       "supersedes", "status", "accepted"):
            self.assertNotIn(hidden, text.lower() if hidden.islower() else text, hidden)
        # the same through feedback after a read
        self.decision("acme-0009", "Plain advice.", binding=False, paths=["src/**"],
                      origin="owner-chat-2026")
        fb = self.post("Read", "src/a.py")["reason"]
        self.assertIn("Plain advice.", fb)
        for hidden in (version, "owner-chat-2026", "binding", "kind:", "origin",
                       "evidence", "version", "accepted"):
            self.assertNotIn(hidden, fb, hidden)


class Descriptive(Project):
    def setUp(self):
        super().setUp()
        self.decision("acme-0010", "Prefer small functions.", binding=False,
                      paths=["src/**"])

    def test_delivered_after_read_as_block_feedback_once(self):
        out = self.post("Read", "src/a.py")
        self.assertEqual(out["decision"], "block")
        self.assertIn("acme-0010", out["reason"])
        self.assertIn("Prefer small functions.", out["reason"])
        self.assertIsNone(self.post("Read", "src/a.py"))
        self.assertIsNone(self.post("Edit", "src/b.py"))

    def test_delivered_after_edit_too(self):
        out = self.post("Edit", "src/a.py")
        self.assertEqual(out["decision"], "block")
        self.assertIn("Prefer small functions.", out["reason"])

    def test_never_denies_before_an_action(self):
        self.assertIsNone(self.pre("Edit", "src/a.py"))
        self.assertIsNone(self.pre("Write", "src/a.py"))
        self.assertIsNone(self.pre("Bash", "ls"))
        # and the descriptive decision still arrives afterwards
        self.assertIn("Prefer small functions.", self.post("Edit", "src/a.py")["reason"])

    def test_mixed_scope_denies_with_binding_only_then_feedback_has_the_rest(self):
        self.decision("acme-0011", "Binding rule text.", paths=["src/**"])
        out = self.pre("Edit", "src/a.py")
        self.assertEqual(verdict(out), "deny")
        self.assertIn("Binding rule text.", reason(out))
        self.assertNotIn("Prefer small functions.", reason(out))
        fb = self.post("Edit", "src/a.py")
        self.assertIn("Prefer small functions.", fb["reason"])
        self.assertNotIn("Binding rule text.", fb["reason"])  # already delivered

    def test_out_of_scope_read_prints_nothing(self):
        self.assertIsNone(self.post("Read", "docs/readme.md"))


class Contexts(Project):
    def setUp(self):
        super().setUp()
        self.decision("acme-0001", "Always --profile acme.", paths=["src/**"])

    def test_subagent_gets_its_own_delivery(self):
        self.assertEqual(verdict(self.pre("Edit", "src/a.py", session="s1")), "deny")
        self.assertIsNone(verdict(self.pre("Edit", "src/a.py", session="s1")))
        self.assertEqual(
            verdict(self.pre("Edit", "src/a.py", session="s1", agent="a1")), "deny"
        )
        self.assertIsNone(
            verdict(self.pre("Edit", "src/a.py", session="s1", agent="a1"))
        )
        self.assertIsNone(verdict(self.pre("Edit", "src/a.py", session="s1")))
        state = self.state()
        self.assertEqual(set(state), {"s1", "s1/a1"})
        self.assertEqual(set(state["s1"]), {"acme-0001"})

    def test_other_session_gets_its_own_delivery(self):
        self.assertEqual(verdict(self.pre("Edit", "src/a.py", session="s1")), "deny")
        self.assertEqual(verdict(self.pre("Edit", "src/a.py", session="s2")), "deny")
        self.assertIsNone(verdict(self.pre("Edit", "src/a.py", session="s2")))
        self.assertEqual(set(self.state()), {"s1", "s2"})

    def test_state_records_the_delivered_version_per_decision(self):
        self.pre("Edit", "src/a.py")
        version = next(d.content_hash for d in load(self.project).decisions)
        self.assertEqual(self.state(), {"s1": {"acme-0001": version}})

    def test_existing_state_of_other_contexts_is_kept(self):
        self.pre("Edit", "src/a.py", session="s1")
        self.pre("Edit", "src/a.py", session="s2")
        self.assertIn("s1", self.state())


class Robustness(Project):
    def setUp(self):
        super().setUp()
        self.decision("acme-0001", "Always --profile acme.", paths=["src/**"])

    def test_corrupt_or_empty_state_is_treated_as_empty(self):
        state = self.project / ".git" / STATE
        for content in ("", "{not json", "[]", "null", '{"s1": "oops"}',
                        '{"s1": {"acme-0001": 5}}', "\x00\xff"):
            with self.subTest(content=content):
                state.write_bytes(content.encode("utf-8", "surrogatepass"))
                out = self.pre("Edit", "src/a.py")
                self.assertEqual(verdict(out), "deny")  # delivered again, not skipped
                self.assertIn("Always --profile acme.", reason(out))
                self.assertIsNone(verdict(self.pre("Edit", "src/a.py")))
                self.assertEqual(set(self.state()), {"s1"})  # rewritten as valid JSON

    def test_one_malformed_file_does_not_stop_others(self):
        (self.project / "docs/decisions/bad.md").write_text(
            "---\nid: acme-bad\nkind: nonsense\n---\n# Bad\n"
        )
        crlf = self.project / "docs/decisions/crlf.md"
        crlf.write_bytes(
            b"\xef\xbb\xbf---\r\nid: acme-0002\r\nkind: policy\r\nstatus: accepted\r\n"
            b"binding: false\r\nsummary: x\r\npaths: [\"src/**\"]\r\n---\r\n# C\r\n"
            b"## How to apply\r\nCRLF-TEXT.\r\n"
        )
        out = self.pre("Edit", "src/a.py")
        self.assertEqual(verdict(out), "deny")
        self.assertIn("Always --profile acme.", reason(out))
        fb = self.post("Edit", "src/a.py")
        self.assertIsNotNone(fb)  # the malformed file did not end delivery

    def test_caps_name_what_was_cut(self):
        for n in range(2, 7):
            self.decision(
                f"acme-000{n}", f"BODY-{n} " + "q" * 5000, paths=["src/**"]
            )
        out = self.pre("Edit", "src/a.py")
        self.assertEqual(verdict(out), "deny")
        text = reason(out)
        self.assertLessEqual(text.count("q"), 12000)  # total cap
        self.assertNotIn("q" * 4001, text)  # per-decision cap
        self.assertIn("q" * 100, text)  # texts are cut, not dropped
        cut = 0
        for n in range(2, 7):
            self.assertIn(f"acme-000{n}", text)  # nothing disappears unnamed
            if f"BODY-{n}" not in text:
                cut += 1
                self.assertIn(f"docs/decisions/acme-000{n}.md", text)
        self.assertGreaterEqual(cut, 1)  # 5 x 4000 cannot fit in 12000

    def test_one_long_decision_is_cut_and_names_its_path(self):
        self.decision("acme-0002", "BODY-2 " + "q" * 5000, paths=["src/**"])
        text = reason(self.pre("Edit", "src/a.py"))
        self.assertNotIn("q" * 4001, text)
        self.assertIn("docs/decisions/acme-0002.md", text)

    def test_internal_error_never_denies(self):
        # the state file is a directory: it can be neither read nor replaced
        (self.project / ".git" / STATE).mkdir()
        out = self.pre("Edit", "src/a.py")
        self.assertNotEqual(verdict(out), "deny")
        self.assertIn("decisions.py lint", out["systemMessage"])
        fb = self.post("Read", "src/a.py")
        self.assertIn("decisions.py lint", fb["systemMessage"])

    @unittest.skipIf(os.geteuid() == 0, "root ignores directory permissions")
    def test_unreadable_root_never_denies(self):
        locked = self.project / "docs" / "locked"
        locked.mkdir()
        self.config(["docs/locked", "docs/decisions"])
        os.chmod(locked, 0)
        self.addCleanup(os.chmod, locked, 0o755)
        out = self.pre("Edit", "src/a.py")  # must not crash
        if out and "systemMessage" in out:
            self.assertIn("decisions.py lint", out["systemMessage"])

    def test_garbage_event_never_denies(self):
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        done = subprocess.run(
            [sys.executable, str(HOOK)], input="not json", capture_output=True,
            text=True, env=env, cwd=str(self.project),
        )
        self.assertEqual(done.returncode, 0)
        self.assertNotIn('"deny"', done.stdout)

    def test_no_config_or_not_a_git_repo_prints_nothing(self):
        (self.project / ".claude" / "noemeo-guard.json").unlink()
        self.assertIsNone(self.pre("Edit", "src/a.py"))
        self.assertIsNone(self.post("Read", "src/a.py"))
        # a config in a directory that is not a Git repo
        with tempfile.TemporaryDirectory() as plain:
            (Path(plain) / ".claude").mkdir()
            (Path(plain) / ".claude" / "noemeo-guard.json").write_text(
                json.dumps({"decision_roots": ["docs"]})
            )
            (Path(plain) / "docs").mkdir()
            (Path(plain) / "docs" / "d.md").write_text(
                "---\nid: acme-0001\nkind: policy\nstatus: accepted\nbinding: true\n"
                'summary: s\npaths: ["**"]\n---\n# D\n## How to apply\nText.\n'
            )
            env = dict(os.environ, CLAUDE_PROJECT_DIR=plain)
            done = subprocess.run(
                [sys.executable, str(HOOK)],
                input=json.dumps({
                    "hook_event_name": "PreToolUse", "session_id": "s1",
                    "tool_name": "Edit",
                    "tool_input": {"file_path": str(Path(plain) / "a.py")},
                    "cwd": plain,
                }),
                capture_output=True, text=True, env=env, cwd=plain,
            )
            self.assertEqual(done.returncode, 0)
            self.assertEqual(done.stdout.strip(), "")


class Registration(unittest.TestCase):
    def test_hooks_json_registers_delivery_on_both_events(self):
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"]

        def matchers(event):
            return [
                entry["matcher"]
                for entry in hooks[event]
                if any("decision_delivery.py" in h["command"] for h in entry["hooks"])
            ]

        self.assertEqual(matchers("PreToolUse"), ["Bash|Edit|Write|MultiEdit|NotebookEdit"])
        self.assertEqual(
            matchers("PostToolUse"), ["Read|Edit|Write|MultiEdit|NotebookEdit"]
        )


class GuardOverlap(Project):
    def test_a_call_the_guard_denies_does_not_consume_the_decision(self):
        (self.project / ".claude" / "noemeo-guard.json").write_text(
            json.dumps({"decision_roots": ["docs/decisions"], "aws_profiles": ["acme-dev"]})
        )
        self.decision("acme-0001", "Plan with the acme account.", commands=["terraform *"])
        self.assertIsNone(verdict(self.pre("Bash", "terraform plan")))  # guard's call
        state_file = self.project / ".git" / STATE
        if state_file.exists():
            self.assertNotIn("acme-0001", self.state().get("s1", {}))
        out = self.pre("Bash", "AWS_PROFILE=acme-dev terraform plan")
        self.assertEqual(verdict(out), "deny")
        self.assertIn("Plan with the acme account.", reason(out))
        self.assertIsNone(verdict(self.pre("Bash", "AWS_PROFILE=acme-dev terraform plan")))


class Python39(Project):
    def test_runs_under_python_3_9_syntax_rules(self):
        py = "/usr/bin/python3"
        if not os.path.exists(py):
            self.skipTest("no /usr/bin/python3 to check Python 3.9 against")
        version = subprocess.run([py, "-c", "import sys;print(sys.version_info[:2]==(3,9))"],
                                 capture_output=True, text=True).stdout.strip()
        if version != "True":
            self.skipTest("/usr/bin/python3 is not Python 3.9")
        self.decision("acme-0001", "Obey acme.", paths=["src/**"])
        done = subprocess.run(
            [py, str(HOOK)],
            input=json.dumps(self.event("PreToolUse", "Edit", "src/a.py")),
            capture_output=True, text=True,
            env=dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project)),
            cwd=str(self.project),
        )
        self.assertNotIn("Traceback", done.stderr)
        self.assertEqual(verdict(json.loads(done.stdout)), "deny", done.stdout + done.stderr)


if __name__ == "__main__":
    unittest.main()
