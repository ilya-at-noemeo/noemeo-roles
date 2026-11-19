"""The decisions index and always-on decisions at session start:
hooks/session_context.sh runs `decisions.py session-start`, which prints
`## Decisions in this repo`, the index, and the full text of current
`always: true` decisions (recorded as delivered). For source compact,
resume or clear it first drops that session's delivery state.

Run: /usr/local/bin/python3 -m unittest tests.test_session_context_decisions

Runs session_context.sh with bash against a throwaway `git init` project,
the SessionStart event on stdin. PATH holds only symlinks to the tools the
script needs (and this interpreter as python3), so `gh` is never found and
nothing touches the network. Names are invented.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPT = ROOT / "hooks" / "session_context.sh"
STATE = "noemeo-decisions-delivered.json"
HEADING = "## Decisions in this repo"
AGREEMENT_HEADING = "## Noemeo working agreement"
TOOLS = ("git", "awk", "sed", "wc", "tr", "head", "tail", "date", "dirname",
         "cat", "env", "bash", "sh", "mktemp", "rm", "mv", "grep", "sort", "cut")


def _value(v):
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (list, tuple)):
        return "[" + ", ".join(f'"{x}"' for x in v) + "]"
    return str(v)


class SessionStart(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        base = Path(tmp.name)
        self.project = base / "acme"
        self.project.mkdir()
        subprocess.run(["git", "init", "-q", str(self.project)], check=True)
        self.config(["docs/decisions"])
        self.bin = base / "bin"
        self.bin.mkdir()
        for tool in TOOLS:
            found = shutil.which(tool)
            if found:
                (self.bin / tool).symlink_to(found)
        (self.bin / "python3").symlink_to(sys.executable)
        self.assertIsNone(shutil.which("gh", path=str(self.bin)))

    def config(self, roots):
        (self.project / ".claude").mkdir(exist_ok=True)
        (self.project / ".claude" / "noemeo-guard.json").write_text(
            json.dumps({"decision_roots": roots})
        )

    def decision(self, id, text=None, *, status="accepted", **extra):
        path = self.project / "docs" / "decisions" / f"{id}.md"
        path.parent.mkdir(parents=True, exist_ok=True)
        fields = {
            "id": id,
            "kind": "policy",
            "status": status,
            "binding": False,
            "summary": f"Summary of {id}",
        }
        fields.update(extra)
        front = "\n".join(f"{k}: {_value(v)}" for k, v in fields.items())
        body = text if text is not None else f"Do {id}."
        path.write_text(f"---\n{front}\n---\n# Record {id}\n\n## How to apply\n{body}\n")
        return path

    def start(self, source="startup", session="s1"):
        event = {"hook_event_name": "SessionStart", "session_id": session, "source": source}
        env = {
            "PATH": str(self.bin),
            "CLAUDE_PROJECT_DIR": str(self.project),
            "HOME": str(self.project),
        }
        done = subprocess.run(
            ["bash", str(SCRIPT)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            env=env,
            cwd=str(self.project),
        )
        self.assertEqual(done.returncode, 0, done.stderr)
        return done.stdout

    def state_path(self):
        return self.project / ".git" / STATE

    def state(self):
        return json.loads(self.state_path().read_text())

    def seed(self, state):
        self.state_path().write_text(json.dumps(state))

    def test_index_is_appended_after_the_working_agreement(self):
        self.decision("0001-widgets", summary="Widgets are blue")
        self.decision("0002-gadgets", summary="Gadgets stay small", tasks=["design"])
        out = self.start()
        self.assertIn(AGREEMENT_HEADING, out)
        self.assertEqual(out.count(HEADING), 1)
        self.assertGreater(out.index(HEADING), out.index(AGREEMENT_HEADING))
        tail = out[out.index(HEADING):]
        self.assertIn("- 0001-widgets: Widgets are blue → docs/decisions/0001-widgets.md", tail)
        self.assertIn("(when: design)", tail)

    def test_the_model_sees_no_metadata_at_session_start(self):
        self.decision("0001-widgets", always=True, paths=["src/**"], binding=True)
        tail = self.start()
        tail = tail[tail.index(HEADING):]
        for hidden in ("kind:", "binding:", "always:", "paths:", "status:", "version"):
            self.assertNotIn(hidden, tail)

    def test_always_decisions_are_delivered_in_full_and_recorded(self):
        self.decision("0001-widgets", "Paint every widget blue.", always=True)
        self.decision("0002-gadgets", "Keep gadgets small.")
        self.decision("0003-gizmos", "Gizmos are retired text.", always=True, status="superseded")
        tail = self.start()
        tail = tail[tail.index(HEADING):]
        self.assertIn("Paint every widget blue.", tail)
        self.assertIn("0001-widgets", tail)
        self.assertNotIn("Keep gadgets small.", tail)
        self.assertNotIn("Gizmos are retired text.", tail)
        state = self.state()
        self.assertEqual(list(state), ["s1"])
        self.assertEqual(list(state["s1"]), ["0001-widgets"])
        self.assertTrue(state["s1"]["0001-widgets"])

    def test_compact_resume_and_clear_reset_this_sessions_state(self):
        self.decision("0001-widgets", "Paint every widget blue.", always=True)
        for source in ("compact", "resume", "clear"):
            with self.subTest(source=source):
                self.seed({
                    "s1": {"old-one": "v1"},
                    "s1/a1": {"old-two": "v2"},
                    "s10": {"other": "v3"},
                    "s2": {"keep": "v4"},
                })
                out = self.start(source)
                state = self.state()
                self.assertNotIn("old-one", state.get("s1", {}))
                self.assertNotIn("s1/a1", state)
                self.assertEqual(state["s2"], {"keep": "v4"})
                self.assertEqual(state["s10"], {"other": "v3"})
                self.assertIn("Paint every widget blue.", out)
                self.assertIn("0001-widgets", state["s1"])

    def test_startup_keeps_state(self):
        self.decision("0001-widgets", always=True)
        self.seed({"s1": {"old-one": "v1"}, "s1/a1": {"old-two": "v2"}, "s2": {"keep": "v4"}})
        self.start("startup")
        state = self.state()
        self.assertEqual(state["s1"]["old-one"], "v1")
        self.assertEqual(state["s1/a1"], {"old-two": "v2"})
        self.assertEqual(state["s2"], {"keep": "v4"})

    def test_no_decision_roots_prints_no_decisions_section(self):
        self.decision("0001-widgets", always=True)
        (self.project / ".claude" / "noemeo-guard.json").write_text("{}")
        out = self.start()
        self.assertIn(AGREEMENT_HEADING, out)
        self.assertNotIn(HEADING, out)
        self.assertFalse(self.state_path().exists())

    def test_no_config_file_prints_no_decisions_section(self):
        (self.project / ".claude" / "noemeo-guard.json").unlink()
        out = self.start()
        self.assertIn("## Repo state at session start", out)
        self.assertNotIn(HEADING, out)


if __name__ == "__main__":
    unittest.main()
