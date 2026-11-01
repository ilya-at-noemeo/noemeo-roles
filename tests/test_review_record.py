"""The reviewer's verdict reaches the record even when its SubagentHandback
call lands in the transcript after SubagentStop has fired (issue #21).

Run: python3 -m unittest discover tests

Transcripts are written in the shape Claude Code uses (JSONL of assistant
and user message entries plus non-message entries); repos are throwaway.
"""

import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest import mock

HOOKS = Path(__file__).resolve().parent.parent / "hooks"
sys.dont_write_bytecode = True
sys.path.insert(0, str(HOOKS))
import review_state  # noqa: E402
from review_record import _final_report, wait_and_record  # noqa: E402
from review_state import latest, snapshot  # noqa: E402


def git(cwd: Path, *args: str) -> str:
    return subprocess.run(
        ["git", "-C", str(cwd), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


# Transcript entry builders.
def assistant(*blocks, stop="tool_use") -> dict:
    return {"type": "assistant", "message": {"role": "assistant", "content": list(blocks), "stop_reason": stop}}


def thinking() -> dict:
    return {"type": "thinking", "thinking": "hmm"}


def text(t: str) -> dict:
    return {"type": "text", "text": t}


def tool_use(id_: str, name: str = "Bash", **input_) -> dict:
    return {"type": "tool_use", "id": id_, "name": name, "input": input_}


def handback(id_: str, message: str) -> dict:
    return assistant(tool_use(id_, "SubagentHandback", message=message))


def result(id_: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": [{"type": "tool_result", "tool_use_id": id_, "content": "ok"}]}}


def prompt(t: str) -> dict:
    return {"type": "user", "message": {"role": "user", "content": t}}


NOISE = [
    {"type": "attachment", "attachment": {"x": 1}},
    {"type": "api-request", "model": "m"},
    {"type": "api-request-blob", "blob": "..."},
]


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name).resolve()  # git reports resolved paths
        self.log = root / "record.log"
        self.transcript = root / "agent.jsonl"
        self.transcript.write_text("")
        git(root, "init", "-q", "--bare", "-b", "main", "origin.git")
        self.repo = root / "work"
        git(root, "clone", "-q", str(root / "origin.git"), str(self.repo))
        for k, v in (("user.name", "t"), ("user.email", "t@example.com")):
            git(self.repo, "config", k, v)
        git(self.repo, "checkout", "-q", "-b", "main")
        (self.repo / "base").write_text("b")
        git(self.repo, "add", "base")
        git(self.repo, "commit", "-q", "-m", "base")
        git(self.repo, "push", "-q", "origin", "main")
        git(self.repo, "remote", "set-head", "origin", "main")
        git(self.repo, "checkout", "-q", "-b", "feat")
        (self.repo / "change").write_text("c")  # an uncommitted change to fingerprint

    def report(self, verdict: str) -> str:
        return f"**{verdict}**: {self.repo}, branch feat\n\nDetails."

    def write(self, *entries: dict) -> None:
        with open(self.transcript, "a") as out:
            for e in entries:
                out.write(json.dumps(e) + "\n")

    def event(self) -> dict:
        return {"agent_id": "a1", "cwd": str(self.repo), "agent_transcript_path": str(self.transcript)}

    def verdict(self) -> str | None:
        row = latest(self.repo, "origin/main")
        return row["verdict"] if row else None

    def log_lines(self) -> list[dict]:
        return [json.loads(x) for x in self.log.read_text().splitlines()] if self.log.exists() else []

    def wait_and_record(self, fingerprints=None, timeout=5.0, poll=0.02, event=None):
        """As the child does: fingerprints taken now, at 'stop'."""
        if fingerprints is None:
            fingerprints = {str(self.repo): snapshot(self.repo)}
        with mock.patch.object(review_state, "LOG", self.log):
            wait_and_record(event or self.event(), fingerprints, timeout=timeout, poll=poll)

    def records(self, repo=None) -> list[dict]:
        path = (repo or self.repo) / ".git" / "noemeo-reviews.jsonl"
        return [json.loads(x) for x in path.read_text().splitlines()] if path.exists() else []


class FinalReport(Base):
    def final(self):
        return _final_report(self.transcript)

    def test_none_while_another_tool_result_ends_the_transcript(self):
        self.write(prompt("review"), assistant(tool_use("t1")), result("t1"))
        self.assertIsNone(self.final())

    def test_none_when_only_thinking_so_far(self):
        self.write(prompt("review"), assistant(thinking()))
        self.assertIsNone(self.final())

    def test_handback_message_once_its_tool_use_is_written(self):
        self.write(prompt("review"), assistant(tool_use("t1")), result("t1"), handback("h1", "**Ready**: x"))
        self.assertEqual(self.final(), "**Ready**: x")

    def test_handback_message_with_its_result(self):
        self.write(prompt("review"), handback("h1", "**Ready**: x"), result("h1"))
        self.assertEqual(self.final(), "**Ready**: x")

    def test_none_after_resume_prompt_and_more_work(self):
        self.write(prompt("review"), handback("h1", "**Not ready**: old"), result("h1"))
        self.write(prompt("fixed it, re-review"))
        self.assertIsNone(self.final())
        self.write(assistant(tool_use("t2")), result("t2"))
        self.assertIsNone(self.final())

    def test_new_report_after_second_handback(self):
        self.write(prompt("review"), handback("h1", "**Not ready**: old"), result("h1"))
        self.write(prompt("again"), assistant(tool_use("t2")), result("t2"))
        self.write(handback("h2", "**Ready**: new"), result("h2"))
        self.assertEqual(self.final(), "**Ready**: new")

    def test_closing_text_reply_counts(self):
        self.write(prompt("review"), assistant(text("**Ready**: x"), stop="end_turn"))
        self.assertEqual(self.final(), "**Ready**: x")

    def test_text_in_a_tool_calling_message_does_not_count(self):
        self.write(prompt("review"), assistant(text("**Ready**: looks fine so far"), tool_use("t1")))
        self.assertIsNone(self.final())

    def test_text_without_a_stop_reason_is_not_a_report_yet(self):
        # The transcript stores one block per entry: a note can be the tail
        # for a while before the tool call that follows it is written.
        self.write(prompt("review"), assistant(text(self.report("Ready")), stop=None))
        self.assertIsNone(self.final())
        self.write(assistant(tool_use("t1")))
        self.assertIsNone(self.final())
        self.write(result("t1"))
        self.assertIsNone(self.final())

    def test_text_without_a_stop_reason_counts_when_it_is_the_last_message(self):
        report = self.report("Ready")
        self.write(prompt("review"), assistant(text(report), stop=None))
        self.assertEqual(_final_report(self.transcript, report), report)
        self.assertIsNone(_final_report(self.transcript, "something else"))

    def test_end_turn_text_counts_whatever_the_last_message(self):
        report = self.report("Ready")
        self.write(prompt("review"), assistant(text(report), stop="end_turn"))
        self.assertEqual(_final_report(self.transcript, "something else"), report)

    def test_non_message_entries_are_ignored(self):
        self.write(prompt("review"), handback("h1", "**Ready**: x"), *NOISE, result("h1"), *NOISE)
        self.assertEqual(self.final(), "**Ready**: x")

    def test_noise_does_not_hide_work_in_progress(self):
        self.write(prompt("review"), handback("h1", "**Not ready**: old"), result("h1"), prompt("again"), *NOISE)
        self.assertIsNone(self.final())


class WaitAndRecord(Base):
    def test_records_a_handback_appended_after_the_wait_starts(self):
        self.write(prompt("review"), assistant(tool_use("t1")), result("t1"))
        timer = threading.Timer(0.3, self.write, [handback("h1", self.report("Ready with nits"))])
        timer.start()
        self.addCleanup(timer.join)
        self.assertIsNone(self.verdict())
        self.wait_and_record()
        self.assertEqual(self.verdict(), "Ready with nits")

    def test_resumed_transcript_records_the_new_verdict_not_the_old(self):
        self.write(prompt("review"), handback("h1", self.report("Not ready")), result("h1"))
        self.write(prompt("fixed, review again"), assistant(tool_use("t2")), result("t2"))
        timer = threading.Timer(0.3, self.write, [handback("h2", self.report("Ready"))])
        timer.start()
        self.addCleanup(timer.join)
        self.wait_and_record()
        self.assertEqual(self.verdict(), "Ready")

    def test_times_out_logging_why_and_records_nothing(self):
        self.write(prompt("review"), handback("h1", self.report("Not ready")), result("h1"))
        self.write(prompt("again"), assistant(tool_use("t2")), result("t2"))
        self.wait_and_record(timeout=0.2)
        self.assertIsNone(self.verdict())
        self.assertEqual(self.records(), [])
        outcomes = [r["outcome"] for r in self.log_lines()]
        self.assertEqual(len(outcomes), 1)
        self.assertTrue(outcomes[0].startswith("nothing recorded: no report"), outcomes)


class StopTimeState(Base):
    def test_report_for_a_repo_no_prompt_or_cwd_named_is_not_recorded_and_logged(self):
        other = Path(self.tmp.name).resolve() / "other"
        git(other.parent, "init", "-q", "-b", "main", str(other))
        self.write(prompt("review"), handback("h1", f"**Ready**: {other}, branch x"))
        self.wait_and_record()  # fingerprints cover only self.repo
        self.assertEqual(self.records(other), [])
        outcomes = [r["outcome"] for r in self.log_lines()]
        self.assertTrue(any(o.startswith(f"nothing recorded for {other}") for o in outcomes), outcomes)

    def test_a_repo_in_the_fingerprints_is_recorded_against_them(self):
        self.write(prompt("review"), handback("h1", self.report("Ready")))
        fps = {str(self.repo): snapshot(self.repo)}
        (self.repo / "change").write_text("edited after stop")
        self.wait_and_record(fps)
        self.assertIsNone(self.verdict())  # the edited tree wasn't reviewed
        self.assertEqual({r["fingerprint"] for r in self.records()}, set(fps[str(self.repo)].values()))


class MainProcess(Base):
    def run_hook(self, event: dict, *args: str) -> subprocess.CompletedProcess:
        env = {**os.environ, "NOEMEO_REVIEW_RECORD_LOG": str(self.log)}
        return subprocess.run(
            [sys.executable, str(HOOKS / "review_record.py"), *args],
            input=json.dumps(event), capture_output=True, text=True, env=env, timeout=30,
        )

    def wait_for(self, want: str, seconds=15.0) -> bool:
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            if self.verdict() == want:
                return True
            time.sleep(0.1)
        return False

    def test_returns_promptly_and_the_detached_child_records_later(self):
        self.write(prompt("review"), assistant(tool_use("t1")), result("t1"))
        started = time.monotonic()
        done = self.run_hook(self.event())
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertLess(time.monotonic() - started, 10)
        self.assertIsNone(self.verdict())  # nothing yet: the report isn't written
        self.write(handback("h1", self.report("Ready")))
        self.assertTrue(self.wait_for("Ready"), self.log_lines())
        time.sleep(1.5)  # the child has exited: it records once
        rows = (self.repo / ".git" / "noemeo-reviews.jsonl").read_text().splitlines()
        self.assertEqual(len({json.loads(r)["verdict"] for r in rows}), 1)
        self.assertEqual(sum("recorded Ready" in r["outcome"] for r in self.log_lines()), 1)

    def test_edits_after_the_stop_are_not_counted_as_reviewed(self):
        self.write(prompt("review"), assistant(tool_use("t1")), result("t1"))
        reviewed = snapshot(self.repo)["origin/main"]
        self.assertEqual(self.run_hook(self.event()).returncode, 0)
        (self.repo / "change").write_text("edited while the report was in flight")
        self.write(handback("h1", self.report("Ready")))
        end = time.monotonic() + 15
        while time.monotonic() < end and not any("recorded Ready" in r["outcome"] for r in self.log_lines()):
            time.sleep(0.1)
        self.assertTrue(any("recorded Ready" in r["outcome"] for r in self.log_lines()), self.log_lines())
        self.assertIsNone(self.verdict())  # the gate's view of the edited tree: unreviewed
        self.assertIn(reviewed, {r["fingerprint"] for r in self.records()})  # the stop-time state is

    def test_a_repo_named_only_in_a_prompt_is_recorded(self):
        other = Path(self.tmp.name).resolve() / "elsewhere"
        git(other.parent, "init", "-q", "-b", "main", str(other))
        git(other, "config", "user.name", "t")
        git(other, "config", "user.email", "t@example.com")
        (other / "f").write_text("x")
        git(other, "add", "f")
        git(other, "commit", "-q", "-m", "i")
        git(other, "update-ref", "refs/remotes/origin/main", "HEAD")
        (other / "g").write_text("y")
        self.write(prompt(f"review the change in {other}"), assistant(tool_use("t1")), result("t1"))
        self.assertEqual(self.run_hook(self.event()).returncode, 0)
        self.write(handback("h1", f"**Ready**: {other}, branch x"))
        end = time.monotonic() + 15
        while time.monotonic() < end and not self.records(other):
            time.sleep(0.1)
        self.assertTrue(self.records(other), self.log_lines())

    def test_malformed_child_input_is_logged(self):
        for stdin in ("not json", json.dumps({"event": {"agent_id": "a1"}})):
            with self.subTest(stdin=stdin):
                env = {**os.environ, "NOEMEO_REVIEW_RECORD_LOG": str(self.log)}
                done = subprocess.run(
                    [sys.executable, str(HOOKS / "review_record.py"), "--wait"],
                    input=stdin, capture_output=True, text=True, env=env, timeout=30,
                )
                self.assertEqual(done.returncode, 0, done.stderr)
                self.assertTrue(self.log_lines()[-1]["outcome"].startswith("nothing recorded: "), self.log_lines())
        self.assertEqual(len(self.log_lines()), 2)

    def test_without_a_transcript_records_from_last_assistant_message_at_once(self):
        event = {
            "agent_id": "a1", "cwd": str(self.repo),
            "last_assistant_message": self.report("Ready with nits"),
            "transcript_path": None, "agent_transcript_path": None,
        }
        done = self.run_hook(event)
        self.assertEqual(done.returncode, 0, done.stderr)
        self.assertEqual(self.verdict(), "Ready with nits")  # synchronously: no waiting
        self.assertTrue(any("recorded Ready with nits" in r["outcome"] for r in self.log_lines()))


class GateDenialNamesTheLog(Base):
    def test_no_review_denial_points_at_the_log(self):
        git(self.repo, "remote", "set-head", "origin", "main")
        event = {"tool_name": "Bash", "cwd": str(self.repo),
                 "tool_input": {"command": "gh pr " + "create --base main"}}
        env = {**os.environ, "NOEMEO_REVIEW_RECORD_LOG": str(self.log)}
        out = subprocess.run(
            [sys.executable, str(HOOKS / "review_gate.py")],
            input=json.dumps(event), capture_output=True, text=True, env=env, check=True,
        )
        self.assertIn('"deny"', out.stdout)
        reason = json.loads(out.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
        self.assertIn(str(self.log), reason)
        self.assertIn("two minutes", reason)


if __name__ == "__main__":
    unittest.main()
