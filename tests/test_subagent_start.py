"""`decisions.py subagent-start`: the SubagentStart hook gives a subagent the
decision index and the `always: true` decisions, as JSON additionalContext,
and records them as delivered under the subagent's own context key.

Run: /opt/homebrew/bin/python3.13 -m pytest tests/test_subagent_start.py

Runs the script as Claude Code does (event JSON on stdin, project in
CLAUDE_PROJECT_DIR) against a throwaway `git init` project; names are
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
CLI = ROOT / "hooks" / "decisions.py"
HOOKS_JSON = ROOT / "hooks" / "hooks.json"
STATE = "noemeo-decisions-delivered.json"
HEADING = "## Decisions in this repo"


def _value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(f'"{x}"' for x in v) + "]"
    return str(v)


class SubagentStart(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.project = Path(tmp.name).resolve() / "acme"
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        self.config(["docs/decisions"])

    def config(self, roots):
        (self.project / ".claude").mkdir(exist_ok=True)
        (self.project / ".claude" / "noemeo-guard.json").write_text(
            json.dumps({"decision_roots": roots})
        )

    def decision(self, id, body=None, **extra):
        path = self.project / "docs" / "decisions" / f"{id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = {"id": id, "kind": "policy", "status": "accepted", "binding": False,
                  "summary": f"Summary of {id}"}
        fields.update(extra)
        front = "\n".join(f"{k}: {_value(v)}" for k, v in fields.items())
        text = body if body is not None else f"Do {id}."
        path.write_text(f"---\n{front}\n---\n# Record {id}\n\n## How to apply\n{text}\n")

    def start(self, event=None, raw=None):
        if event is None:
            event = {"hook_event_name": "SubagentStart", "session_id": "s1",
                     "agent_id": "a1", "agent_type": "general-purpose",
                     "cwd": str(self.project)}
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        return subprocess.run(
            [sys.executable, str(CLI), "subagent-start"],
            input=json.dumps(event) if raw is None else raw,
            capture_output=True, text=True, env=env, cwd=str(self.project.parent),
        )

    def context(self, proc):
        self.assertEqual(proc.returncode, 0, proc.stderr)
        out = json.loads(proc.stdout)
        self.assertEqual(set(out), {"hookSpecificOutput"})
        self.assertEqual(out["hookSpecificOutput"]["hookEventName"], "SubagentStart")
        return out["hookSpecificOutput"]["additionalContext"]

    def state(self):
        return json.loads((self.project / ".git" / STATE).read_text())

    def test_emits_the_index_and_always_decisions_as_additional_context(self):
        self.decision("0001-widgets", "Paint every widget blue.", always=True)
        self.decision("0002-gadgets", "Keep gadgets small.", tasks=["design"])
        text = self.context(self.start())
        self.assertIn(HEADING, text)
        self.assertIn("- 0001-widgets: Summary of 0001-widgets → docs/decisions/0001-widgets.md", text)
        self.assertIn("- 0002-gadgets: Summary of 0002-gadgets", text)
        self.assertIn("Paint every widget blue.", text)
        self.assertNotIn("Keep gadgets small.", text)  # only the index names it

    def test_content_matches_what_session_start_prints(self):
        self.decision("0001-widgets", "Paint every widget blue.", always=True)
        self.decision("0002-gadgets", "Keep gadgets small.")
        sub = self.context(self.start())
        env = dict(os.environ, CLAUDE_PROJECT_DIR=str(self.project))
        sess = subprocess.run(
            [sys.executable, str(CLI), "session-start"],
            input=json.dumps({"hook_event_name": "SessionStart", "session_id": "other",
                              "source": "startup"}),
            capture_output=True, text=True, env=env,
        ).stdout
        self.assertEqual(sub.strip(), sess.strip())

    def test_the_subagent_sees_no_metadata(self):
        self.decision("0001-widgets", always=True, paths=["src/**"], binding=True,
                      origin="owner-chat-2026")
        text = self.context(self.start())
        for hidden in ("kind:", "binding:", "always:", "paths:", "status:", "version",
                       "owner-chat-2026", "content_hash"):
            self.assertNotIn(hidden, text)

    def test_records_always_decisions_under_the_subagents_context_key(self):
        from_hooks = str(ROOT / "hooks")
        sys.path.insert(0, from_hooks)
        try:
            from decisions import load
        finally:
            sys.path.remove(from_hooks)
        self.decision("0001-widgets", "Paint every widget blue.", always=True)
        self.decision("0002-gadgets", "Keep gadgets small.")
        self.context(self.start())
        digest = next(d.content_hash for d in load(self.project).decisions
                      if d.id == "0001-widgets")
        self.assertEqual(self.state(), {"s1/a1": {"0001-widgets": digest}})

    def test_does_not_reset_or_touch_the_session_state(self):
        self.decision("0001-widgets", "Paint every widget blue.", always=True)
        (self.project / ".git" / STATE).write_text(
            json.dumps({"s1": {"acme-9": "abc123abc123"}, "s1/other": {"acme-8": "def"}})
        )
        event = {"hook_event_name": "SubagentStart", "session_id": "s1", "agent_id": "a1",
                 "source": "compact"}
        self.context(self.start(event))
        state = self.state()
        self.assertEqual(state["s1"], {"acme-9": "abc123abc123"})
        self.assertEqual(state["s1/other"], {"acme-8": "def"})
        self.assertIn("s1/a1", state)

    def test_without_decision_roots_prints_nothing_and_exits_0(self):
        self.decision("0001-widgets", always=True)
        self.config([])
        proc = self.start()
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))
        (self.project / ".claude" / "noemeo-guard.json").unlink()
        proc = self.start()
        self.assertEqual((proc.returncode, proc.stdout), (0, ""))
        self.assertFalse((self.project / ".git" / STATE).exists())

    def test_malformed_or_empty_stdin_never_fails(self):
        self.decision("0001-widgets", always=True)
        for raw in ("", "not json", "[1, 2]", "null", '{"session_id": 5, "agent_id": ["x"]}'):
            with self.subTest(raw=raw):
                proc = self.start(raw=raw)
                self.assertEqual(proc.returncode, 0, proc.stderr)
                if proc.stdout.strip():
                    json.loads(proc.stdout)  # whatever is printed is valid hook JSON

    def test_any_failure_exits_0_with_nothing_on_stdout(self):
        self.decision("0001-widgets", always=True)
        (self.project / ".claude" / "noemeo-guard.json").write_text("{nope")
        proc = self.start()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        self.assertEqual(proc.stdout, "")

    def test_unwritable_state_still_exits_0_without_raw_text(self):
        self.decision("0001-widgets", "Paint every widget blue.", always=True)
        (self.project / ".git" / STATE).mkdir()  # a directory where the file should be
        proc = self.start()
        self.assertEqual(proc.returncode, 0, proc.stderr)
        if proc.stdout.strip():
            json.loads(proc.stdout)


class Registration(unittest.TestCase):
    def test_hooks_json_runs_subagent_start_for_every_subagent(self):
        hooks = json.loads(HOOKS_JSON.read_text())["hooks"]
        entries = hooks["SubagentStart"]
        self.assertEqual(len(entries), 1)
        self.assertNotIn("matcher", entries[0])
        (hook,) = entries[0]["hooks"]
        self.assertEqual(hook["type"], "command")
        self.assertEqual(
            hook["command"], '"${CLAUDE_PLUGIN_ROOT}"/hooks/decisions.py subagent-start')
        self.assertEqual(hook["timeout"], 15)

    def test_hooks_json_description_mentions_subagents(self):
        description = json.loads(HOOKS_JSON.read_text())["description"]
        self.assertRegex(description, r"(?i)(index[^.;]*subagent|subagent[^.;]*(index|decision))")


if __name__ == "__main__":
    unittest.main()
