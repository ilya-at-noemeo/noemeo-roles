#!/usr/bin/env python3
"""SubagentStop hook for noemeo-code-reviewer: record its verdict against
a fingerprint of each repo it names (review_state.py), so review_gate.py
can tell whether the change about to become a PR was reviewed as it is.

The reviewer's report opens with a verdict line naming the repo by
absolute path; every existing git repo path in that report is recorded,
falling back to the session's working directory. Never blocks.

The report is the subagent's last message, or, when it hands its report
back with a tool call (SubagentHandback) instead of a closing message,
that call's text: the last message then holds no verdict, so it is read
from the subagent's own transcript.
"""

import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ beside the hooks
sys.path.insert(0, str(Path(__file__).parent))
from review_state import record, toplevel  # noqa: E402

VERDICTS = ("Not ready", "Ready with nits", "Ready")


def _verdict(message: str) -> str | None:
    return next((v for v in VERDICTS if v in message[:400]), None)


def _transcript(event: dict) -> Path | None:
    """The subagent's own transcript: given by the event, or next to the
    session's (<session>/subagents/agent-<id>.jsonl)."""
    if event.get("agent_transcript_path"):
        return Path(event["agent_transcript_path"])
    session, agent = event.get("transcript_path"), event.get("agent_id")
    if session and agent:
        return Path(session).with_suffix("") / "subagents" / f"agent-{agent}.jsonl"
    return None


def _handback(path: Path | None) -> str:
    """The text of the subagent's last report in its transcript: a
    SubagentHandback call's message, or its last text reply."""
    if path is None or not path.is_file():
        return ""
    for line in reversed(path.read_text().splitlines()):
        try:
            entry = json.loads(line)
        except json.JSONDecodeError:
            continue
        if entry.get("type") != "assistant":
            continue
        content = entry.get("message", {}).get("content")
        if isinstance(content, str):
            return content
        for block in reversed(content or []):
            if block.get("type") == "tool_use" and block.get("name") == "SubagentHandback":
                return str(block.get("input", {}).get("message", ""))
            if block.get("type") == "text" and block.get("text", "").strip():
                return block["text"]
    return ""


def main() -> None:
    event = json.load(sys.stdin)
    message = event.get("last_assistant_message") or ""
    if _verdict(message) is None:
        message = _handback(_transcript(event)) or message
    verdict = _verdict(message)
    if verdict is None:
        return  # not a finished review (asked a question, or failed)
    repos = []
    for candidate in re.findall(r"(/[\w.@~+-]+(?:/[\w.@~+-]+)+)", message):
        candidate = candidate.rstrip(".")  # a path ending a sentence
        repo = toplevel(Path(candidate)) if Path(candidate).exists() else None
        if repo and repo not in repos:
            repos.append(repo)
    if not repos:
        repo = toplevel(Path(event.get("cwd") or "."))
        repos = [repo] if repo else []
    first_line = message.strip().splitlines()[0] if message.strip() else ""
    for repo in repos:
        record(repo, verdict, first_line)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 -- a recording failure must never break the session
        print(f"review_record: {e}", file=sys.stderr)
