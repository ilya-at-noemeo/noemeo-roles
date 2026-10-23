"""The SubagentStop usage hook: what it totals from a subagent's transcript
and what it still logs when pieces are missing or malformed.

Run: python3 -m unittest discover tests

Each test runs hooks/agent_usage.py as a subprocess with the event on stdin
and NOEMEO_AGENT_USAGE_LOG pointing into a temp dir (never the real ~/.claude).
"""

import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

HOOK = Path(__file__).resolve().parent.parent / "hooks" / "agent_usage.py"


def assistant(ts, msg_id, blocks, model="claude-opus-5-5", usage=None):
    return {
        "type": "assistant",
        "timestamp": ts,
        "uuid": f"u-{ts}",
        "message": {
            "id": msg_id,
            "model": model,
            "content": blocks,
            "usage": usage
            or {
                "input_tokens": 2,
                "cache_creation_input_tokens": 24245,
                "cache_read_input_tokens": 100,
                "output_tokens": 8,
            },
        },
    }


def tool_use(n):
    return {"type": "tool_use", "id": f"toolu_{n}", "name": "Read", "input": {"file_path": "/x"}}


TEXT = {"type": "text", "text": "hi"}


def user(ts):
    return {"type": "user", "timestamp": ts, "message": {"role": "user", "content": "go"}}


class AgentUsage(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.log = self.root / "logs" / "usage.jsonl"
        self.session = self.root / "proj" / "sess1.jsonl"
        self.sub = self.root / "proj" / "sess1" / "subagents"
        self.sub.mkdir(parents=True)

    def write_transcript(self, entries, name="agent-a1.jsonl", raw=None):
        path = self.sub / name
        path.write_text(raw if raw is not None else "".join(json.dumps(e) + "\n" for e in entries))
        return path

    def write_meta(self, path, meta):
        path.with_suffix(".meta.json").write_text(json.dumps(meta))

    def run_hook(self, event=None, stdin=None):
        env = {**os.environ, "NOEMEO_AGENT_USAGE_LOG": str(self.log)}
        data = stdin if stdin is not None else json.dumps(event)
        proc = subprocess.run(
            [sys.executable, str(HOOK)], input=data, capture_output=True, text=True, env=env
        )
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc

    def lines(self):
        if not self.log.exists():
            return []
        return [json.loads(x) for x in self.log.read_text().splitlines()]

    def default_event(self, **extra):
        return {
            "session_id": "sess1",
            "agent_id": "a1",
            "transcript_path": str(self.session),
            **extra,
        }

    # 1
    def test_message_id_spanning_entries_is_counted_once(self):
        self.write_transcript(
            [
                user("2026-10-22T16:49:40.000Z"),
                assistant("2026-10-22T16:49:46.023Z", "msg_1", [TEXT]),
                assistant("2026-10-22T16:49:46.500Z", "msg_1", [tool_use(1)]),
                assistant(
                    "2026-10-22T16:49:50.000Z",
                    "msg_2",
                    [TEXT],
                    usage={"input_tokens": 5, "cache_creation_input_tokens": 1,
                           "cache_read_input_tokens": 10, "output_tokens": 20},
                ),
            ]
        )
        self.run_hook(self.default_event())
        (rec,) = self.lines()
        self.assertEqual(
            rec["tokens"],
            {"input_tokens": 7, "cache_creation_input_tokens": 24246,
             "cache_read_input_tokens": 110},
        )

    # 2
    def test_tool_calls_models_and_seconds(self):
        self.write_transcript(
            [
                user("2026-10-22T16:49:40.000Z"),
                assistant("2026-10-22T16:49:46.000Z", "msg_1", [tool_use(1), tool_use(2)]),
                user("2026-10-22T16:49:50.000Z"),
                assistant("2026-10-22T16:50:10.000Z", "msg_2", [TEXT, tool_use(3)], model="claude-haiku-5"),
                assistant("2026-10-22T16:50:40.000Z", "msg_3", [TEXT]),
            ]
        )
        self.run_hook(self.default_event())
        (rec,) = self.lines()
        self.assertEqual(rec["tool_calls"], 3)
        self.assertEqual(rec["models"], ["claude-haiku-5", "claude-opus-5-5"])
        self.assertEqual(rec["seconds"], 60)

    def test_output_chars_measure_what_the_agent_wrote(self):
        # Output tokens in a transcript are stream-start values, so the size
        # of what was written is logged instead: text, thinking, tool input.
        thinking = {"type": "thinking", "thinking": "abcd"}
        self.write_transcript(
            [
                assistant("2026-10-22T16:49:46.000Z", "msg_1", [thinking]),
                assistant("2026-10-22T16:49:46.500Z", "msg_1", [TEXT, tool_use(1)]),
            ]
        )
        self.run_hook(self.default_event())
        (rec,) = self.lines()
        self.assertEqual(rec["output_chars"], 4 + 2 + len(json.dumps({"file_path": "/x"})))
        self.assertNotIn("output_tokens", rec["tokens"])

    def test_tool_calls_in_repeated_message_id_entries_all_count(self):
        self.write_transcript(
            [
                assistant("2026-10-22T16:49:46.000Z", "msg_1", [tool_use(1)]),
                assistant("2026-10-22T16:49:47.000Z", "msg_1", [tool_use(2)]),
            ]
        )
        self.run_hook(self.default_event())
        self.assertEqual(self.lines()[0]["tool_calls"], 2)

    # 3
    def test_agent_type_from_event_else_meta_and_description_from_meta(self):
        path = self.write_transcript([user("2026-10-22T16:49:40.000Z")])
        self.write_meta(path, {"agentType": "noemeo:noemeo-code-reviewer", "description": "Review X"})
        self.run_hook(self.default_event())
        self.run_hook(self.default_event(agent_type="noemeo:other"))
        first, second = self.lines()
        self.assertEqual(first["agent_type"], "noemeo:noemeo-code-reviewer")
        self.assertEqual(first["description"], "Review X")
        self.assertEqual(second["agent_type"], "noemeo:other")
        self.assertEqual(second["description"], "Review X")

    # 4
    def test_transcript_found_via_agent_transcript_path(self):
        other = self.root / "elsewhere" / "t.jsonl"
        other.parent.mkdir()
        other.write_text(json.dumps(assistant("2026-10-22T16:49:46.000Z", "m", [tool_use(1)])) + "\n")
        self.write_meta(other, {"agentType": "x:y", "description": "D"})
        # Default location holds a different transcript that must not be used.
        self.write_transcript([assistant("2026-10-22T16:49:46.000Z", "m", [tool_use(1), tool_use(2)])])
        self.run_hook(self.default_event(agent_transcript_path=str(other)))
        (rec,) = self.lines()
        self.assertEqual(rec["tool_calls"], 1)
        self.assertEqual(rec["agent_type"], "x:y")

    def test_transcript_found_from_session_path_and_agent_id(self):
        self.write_transcript([assistant("2026-10-22T16:49:46.000Z", "m", [tool_use(1), tool_use(2)])])
        self.run_hook(self.default_event())
        self.assertEqual(self.lines()[0]["tool_calls"], 2)

    # 5
    def test_missing_transcript_still_logs_without_usage_fields(self):
        self.run_hook(self.default_event(agent_type="a:b"))
        (rec,) = self.lines()
        self.assertEqual(rec["agent_id"], "a1")
        self.assertEqual(rec["session_id"], "sess1")
        self.assertEqual(rec["agent_type"], "a:b")
        self.assertIsNone(rec["description"])
        for key in ("tokens", "tool_calls", "models", "seconds"):
            self.assertNotIn(key, rec)

    def test_event_without_any_transcript_hint_still_logs(self):
        self.run_hook({"session_id": "s", "agent_id": "a1"})
        (rec,) = self.lines()
        self.assertEqual(rec["session_id"], "s")
        self.assertNotIn("tokens", rec)

    def test_missing_meta_file_still_logs_usage(self):
        self.write_transcript([assistant("2026-10-22T16:49:46.000Z", "m", [TEXT])])
        self.run_hook(self.default_event())
        (rec,) = self.lines()
        self.assertIsNone(rec["agent_type"])
        self.assertIsNone(rec["description"])
        self.assertEqual(rec["tokens"]["input_tokens"], 2)

    def test_malformed_meta_file_still_logs(self):
        path = self.write_transcript([assistant("2026-10-22T16:49:46.000Z", "m", [TEXT])])
        path.with_suffix(".meta.json").write_text("{not json")
        self.run_hook(self.default_event())
        (rec,) = self.lines()
        self.assertIsNone(rec["description"])
        self.assertEqual(rec["tokens"]["input_tokens"], 2)

    def test_malformed_transcript_lines_are_skipped(self):
        good = json.dumps(assistant("2026-10-22T16:49:46.000Z", "m", [tool_use(1)]))
        later = json.dumps(assistant("2026-10-22T16:49:56.000Z", "m2", [TEXT]))
        self.write_transcript(None, raw=f"{{broken\n{good}\n\nnot json at all\n{later}\n")
        self.run_hook(self.default_event())
        (rec,) = self.lines()
        self.assertEqual(rec["tool_calls"], 1)
        self.assertEqual(rec["tokens"]["input_tokens"], 4)
        self.assertEqual(rec["seconds"], 10)

    # A line that is valid JSON but not an object (e.g. `[1,2]`) is skipped;
    # it once raised in usage() and dropped the whole record.
    def test_non_object_json_line_does_not_drop_the_record(self):
        good = json.dumps(assistant("2026-10-22T16:49:46.000Z", "m", [tool_use(1)]))
        self.write_transcript(None, raw=f"[1,2]\n{good}\n")
        self.run_hook(self.default_event())
        (rec,) = self.lines()
        self.assertEqual(rec["tool_calls"], 1)

    def test_malformed_event_exits_zero_and_logs_nothing(self):
        for bad in ("", "not json", "[1, 2]"):
            proc = self.run_hook(stdin=bad)
            self.assertIn("agent_usage", proc.stderr)
        self.assertEqual(self.lines(), [])

    # 6
    def test_each_stop_appends_a_line(self):
        self.write_transcript([assistant("2026-10-22T16:49:46.000Z", "m", [TEXT])])
        self.run_hook(self.default_event())
        self.write_transcript(
            [
                assistant("2026-10-22T16:49:46.000Z", "m", [TEXT]),
                assistant("2026-10-22T16:49:56.000Z", "m2", [TEXT]),
            ]
        )
        self.run_hook(self.default_event())
        first, second = self.lines()
        self.assertEqual(first["tokens"]["input_tokens"], 2)
        self.assertEqual(second["tokens"]["input_tokens"], 4)

    def test_repo_is_git_toplevel_of_cwd_or_null(self):
        repo = self.root / "repo"
        (repo / "sub").mkdir(parents=True)
        subprocess.run(["git", "-C", str(repo), "init", "-q"], check=True)
        plain = self.root / "plain"
        plain.mkdir()
        self.run_hook(self.default_event(cwd=str(repo / "sub")))
        self.run_hook(self.default_event(cwd=str(plain)))
        self.run_hook(self.default_event())
        inside, outside, nocwd = self.lines()
        self.assertEqual(Path(inside["repo"]).resolve(), repo.resolve())
        self.assertIsNone(outside["repo"])
        self.assertIsNone(nocwd["repo"])


if __name__ == "__main__":
    unittest.main()
