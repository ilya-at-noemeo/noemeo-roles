#!/usr/bin/env python3
"""SubagentStop hook: log what each subagent used -- one JSON line per
stop, appended to ~/.claude/noemeo-agent-usage.jsonl (or the path in
NOEMEO_AGENT_USAGE_LOG). Never blocks.

Each line: time, session, agent id and type, the task description it
was given, the repo it worked in (its transcript's last working
directory, else the event's), its model(s), input token counts
(input, cache writes, cache reads), the characters it wrote, tool
calls, and the span from its first to its last transcript entry. All of
it is read from the subagent's own transcript
(<session>/subagents/agent-<id>.jsonl) and the .meta.json beside it.

Output tokens aren't logged: the transcript usually stores a streamed
message's usage as it was when the stream started, when the input and
cache counts are final but output has barely begun (a few tokens for a
10,000-character file write); only some entries carry final counts, so
a sum would mislead. `output_chars` -- the length of the text,
thinking and tool-call input the agent wrote -- is measured instead; it
is a size, not a token count.

A resumed agent (SendMessage) appends to the same transcript, so each
stop logs its totals so far: the last line per agent id is its total.
"""

import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

DEFAULT_LOG = Path.home() / ".claude" / "noemeo-agent-usage.jsonl"
TOKEN_FIELDS = ("input_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")


def written_chars(block: dict) -> int:
    if block.get("type") == "text":
        return len(block.get("text") or "")
    if block.get("type") == "thinking":
        return len(block.get("thinking") or "")
    if block.get("type") == "tool_use":
        return len(json.dumps(block.get("input") or {}))
    return 0


def transcript_path(event: dict) -> Path | None:
    if event.get("agent_transcript_path"):
        return Path(event["agent_transcript_path"])
    session, agent = event.get("transcript_path"), event.get("agent_id")
    if session and agent:
        return Path(session).with_suffix("") / "subagents" / f"agent-{agent}.jsonl"
    return None


def usage(path: Path) -> dict:
    """Totals over the transcript, read line by line. An API message can
    span several entries (one per content block) carrying the same usage,
    so each message id counts once. A malformed entry is skipped, not
    allowed to lose the whole line."""
    tokens = dict.fromkeys(TOKEN_FIELDS, 0)
    models, seen, tool_calls, output_chars, times = set(), set(), 0, 0, []
    cwd = None
    with path.open(errors="replace") as lines:
        for line in lines:
            try:
                entry = json.loads(line)
                if not isinstance(entry, dict):
                    continue
                if isinstance(entry.get("timestamp"), str):
                    times.append(datetime.fromisoformat(entry["timestamp"].replace("Z", "+00:00")))
                if isinstance(entry.get("cwd"), str):
                    cwd = entry["cwd"]
                message = entry.get("message")
                if entry.get("type") != "assistant" or not isinstance(message, dict):
                    continue
                content = message.get("content")
                if isinstance(content, list):
                    blocks = [b for b in content if isinstance(b, dict)]
                    tool_calls += sum(b.get("type") == "tool_use" for b in blocks)
                    output_chars += sum(written_chars(b) for b in blocks)
                key = str(message.get("id") or entry.get("uuid"))
                if key in seen:
                    continue
                seen.add(key)
                if isinstance(message.get("model"), str):
                    models.add(message["model"])
                counts = message.get("usage") if isinstance(message.get("usage"), dict) else {}
                for field in TOKEN_FIELDS:
                    tokens[field] += int(counts.get(field) or 0)
            except (ValueError, TypeError, AttributeError):
                continue
    seconds = round((max(times) - min(times)).total_seconds()) if len(times) >= 2 else None
    return {
        "cwd": cwd,
        "models": sorted(models),
        "tokens": tokens,
        "output_chars": output_chars,
        "tool_calls": tool_calls,
        "seconds": seconds,
    }


def repo_of(cwd: str | None) -> str | None:
    if not cwd:
        return None
    try:
        return subprocess.run(
            ["git", "-C", cwd, "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            timeout=5,
        ).stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return None


def main() -> None:
    event = json.load(sys.stdin)
    path = transcript_path(event)
    meta = {}
    if path is not None:
        try:
            meta = json.loads(path.with_suffix(".meta.json").read_text())
        except (OSError, ValueError):
            meta = {}
        if not isinstance(meta, dict):
            meta = {}
    record = {
        "time": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "session_id": event.get("session_id"),
        "agent_id": event.get("agent_id"),
        "agent_type": event.get("agent_type") or meta.get("agentType"),
        "description": meta.get("description"),
    }
    totals = usage(path) if path is not None and path.is_file() else {}
    record["repo"] = repo_of(totals.pop("cwd", None) or event.get("cwd"))
    record.update(totals)
    log = Path(os.environ.get("NOEMEO_AGENT_USAGE_LOG") or DEFAULT_LOG)
    log.parent.mkdir(parents=True, exist_ok=True)
    with log.open("a") as f:
        f.write(json.dumps(record) + "\n")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa: BLE001 -- logging must never break the session
        print(f"agent_usage: {e}", file=sys.stderr)
