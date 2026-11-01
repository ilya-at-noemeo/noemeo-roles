#!/usr/bin/env python3
"""SubagentStop hook for noemeo-code-reviewer: record its verdict against
a fingerprint of each repo it names (review_state.py), so review_gate.py
can tell whether the change about to become a PR was reviewed as it is.

The reviewer's report opens with a verdict line naming the repo by
absolute path; each git repo the report names is recorded (see below
for which), falling back to the session's working directory. Never
blocks.

The report is read from the subagent's own transcript: its last
SubagentHandback call's message, or its closing text reply. When the
subagent hands its report back with SubagentHandback, the hook fires
before that call (and up to the last half-minute of the run) reaches the
transcript, and `last_assistant_message` still holds an earlier report
(a resumed reviewer's previous verdict) or none. So the hook passes the
event to a detached copy of itself, which waits until the transcript
ends with this run's report, then records it. Only an event with no
transcript (Codex) is recorded from `last_assistant_message`, at once.

What is recorded is the state when the reviewer stopped, not when its
report arrives: edits made meanwhile weren't reviewed. The hook
fingerprints, at once, the session's repo and every repo its prompts
name by absolute path, and the copy records those fingerprints; a repo
the report names but no prompt did isn't recorded.

Each stop's outcome -- what was recorded, or why nothing was -- is
appended to review_state.LOG, which the gate names when it finds no
review.
"""

import json
import re
import subprocess
import sys
import time
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ beside the hooks
sys.path.insert(0, str(Path(__file__).parent))
from review_state import log, record, record_snapshot, snapshot, toplevel  # noqa: E402

VERDICTS = ("Not ready", "Ready with nits", "Ready")
WAIT_SECONDS = 120  # longest to wait for the report to reach the transcript
PATHS = re.compile(r"(/[\w.@~+-]+(?:/[\w.@~+-]+)+)")


def _verdict(message: str) -> str | None:
    return next((v for v in VERDICTS if v in message[:400]), None)


def _repos(text: str) -> list[Path]:
    """The git repos that absolute paths in the text lie in, in order."""
    repos = []
    for candidate in PATHS.findall(text):
        candidate = candidate.rstrip(".")  # a path ending a sentence
        repo = toplevel(Path(candidate)) if Path(candidate).exists() else None
        if repo and repo not in repos:
            repos.append(repo)
    return repos


def _transcript(event: dict) -> Path | None:
    """The subagent's own transcript: given by the event, or next to the
    session's (<session>/subagents/agent-<id>.jsonl)."""
    if event.get("agent_transcript_path"):
        return Path(event["agent_transcript_path"])
    session, agent = event.get("transcript_path"), event.get("agent_id")
    if session and agent:
        return Path(session).with_suffix("") / "subagents" / f"agent-{agent}.jsonl"
    return None


def _entries(path: Path):
    for line in path.read_text().splitlines():
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        message = entry.get("message") if isinstance(entry, dict) else None
        if isinstance(message, dict):  # not attachments or API request records
            yield entry.get("type"), message


def _prompts(path: Path) -> str:
    """The prompts the subagent was given, the first and any that resumed it."""
    return "\n".join(m["content"] for kind, m in _entries(path) if kind == "user" and isinstance(m.get("content"), str))


def _final_report(path: Path, last_message: str = "") -> str | None:
    """The run's report once the transcript ends with it: the last
    SubagentHandback call's message, or a closing text reply, with nothing
    after it but that call's result. None while the run's report is still
    to be written -- the transcript then ends with work in progress, or
    with an earlier run's report followed by the prompt that resumed it.

    The transcript stores one block per entry, so a text block a tool call
    will follow can be its last entry for a while. Text counts as closing
    only when its turn ended there, or when it is the event's
    `last_assistant_message`, which is up to date for a run that ends
    with a text reply."""
    report, handback_id = None, None
    for kind, message in _entries(path):
        content = message.get("content")
        if kind == "user":
            blocks = [b for b in content if isinstance(b, dict)] if isinstance(content, list) else []
            handback_result = bool(blocks) and all(
                b.get("type") == "tool_result" and b.get("tool_use_id") == handback_id for b in blocks
            )
            if not (handback_id and handback_result):
                report, handback_id = None, None  # another tool's result or a new prompt: the run goes on
        elif kind == "assistant":
            if isinstance(content, str):
                report, handback_id = content, None
                continue
            for block in content or []:
                if not isinstance(block, dict):
                    continue
                if block.get("type") == "tool_use" and block.get("name") == "SubagentHandback":
                    report = str(block.get("input", {}).get("message", ""))
                    handback_id = block.get("id")
                elif block.get("type") == "tool_use":
                    report, handback_id = None, None
                elif block.get("type") == "text" and block.get("text", "").strip():
                    text = block["text"]
                    closing = message.get("stop_reason") in ("end_turn", "stop_sequence")
                    closing = closing or (bool(last_message.strip()) and text.strip() == last_message.strip())
                    report, handback_id = (text if closing else None), None
    return report


def _record(event: dict, message: str, fingerprints: dict[str, dict[str, str]] | None = None) -> None:
    """Record the report's verdict for each repo it names: against the
    fingerprints taken at stop when given, else against the repo now."""
    verdict = _verdict(message)
    if verdict is None:
        # Not a finished review (asked a question, or failed).
        log(event, "nothing recorded: the report has no verdict", message[:200])
        return
    repos = _repos(message)
    if not repos:
        repo = toplevel(Path(event.get("cwd") or "."))
        repos = [repo] if repo else []
    if not repos:
        log(event, "nothing recorded: the report names no git repo", message[:200])
        return
    first_line = message.strip().splitlines()[0]
    for repo in repos:
        if fingerprints is None:
            bases = record(repo, verdict, first_line)
        elif str(repo) in fingerprints:
            bases = record_snapshot(repo, verdict, first_line, fingerprints[str(repo)])
        else:
            log(
                event,
                f"nothing recorded for {repo}: no prompt named it, so its state when the "
                "reviewer stopped is unknown; name it by absolute path and review again",
            )
            continue
        log(event, f"recorded {verdict} for {repo} against {', '.join(bases) or 'no base'}")


def wait_and_record(
    event: dict, fingerprints: dict[str, dict[str, str]], timeout: float = WAIT_SECONDS, poll: float = 1.0
) -> None:
    """Record the run's report against the fingerprints taken at stop,
    once the report reaches the transcript. A closing reply without a
    verdict is waited past too, and logged as such only at the deadline."""
    path = _transcript(event)
    last_message = event.get("last_assistant_message") or ""
    deadline = time.monotonic() + timeout
    while True:
        report = _final_report(path, last_message) if path and path.is_file() else None
        if report is not None and _verdict(report) is not None:
            break
        if time.monotonic() >= deadline:
            break
        time.sleep(poll)
    if report is None:
        log(event, f"nothing recorded: no report reached {path} within {timeout:.0f}s")
        return
    _record(event, report, fingerprints)


def main() -> None:
    if sys.argv[1:] == ["--wait"]:
        event = {}
        try:
            given = json.load(sys.stdin)
            event = given["event"]
            wait_and_record(event, given["fingerprints"])
        except Exception as e:  # noqa: BLE001 -- logged where the gate points, not lost on stderr
            log(event, f"nothing recorded: {type(e).__name__}: {e}")
        return
    event = json.load(sys.stdin)
    path = _transcript(event)
    if path is None:
        _record(event, event.get("last_assistant_message") or "")
        return
    # Detached, with no pipe back, so the session doesn't wait for it.
    # Started before the fingerprints are taken: if the hook is cut short
    # meanwhile, the copy reads a broken event and logs that.
    child = subprocess.Popen(
        [sys.executable, __file__, "--wait"],
        stdin=subprocess.PIPE,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        start_new_session=True,
    )
    repos = [toplevel(Path(event.get("cwd") or "."))]
    repos += _repos(_prompts(path)) if path.is_file() else []
    fingerprints = {str(r): snapshot(r) for r in dict.fromkeys(repos) if r}
    log(event, f"waiting for the report; state taken for {', '.join(fingerprints) or 'no repo'}")
    child.stdin.write(json.dumps({"event": event, "fingerprints": fingerprints}).encode())
    child.stdin.close()


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 -- a recording failure must never break the session
        print(f"review_record: {e}", file=sys.stderr)
