#!/usr/bin/env python3
"""Translate Codex events to the existing Noemeo hook implementations.

Installed under noemeo-roles/codex/. No changes to Claude's hook wiring.
"""

import json
import os
from pathlib import Path
import re
import subprocess
import sys

ROOT = Path(__file__).resolve().parent.parent
HOOKS = ROOT / "hooks"


def run(name, event, cwd, timeout=30):
    env = dict(os.environ, CLAUDE_PROJECT_DIR=str(cwd), PYTHONDONTWRITEBYTECODE="1")
    executable = "bash" if name.endswith(".sh") else sys.executable
    result = subprocess.run(
        [executable, str(HOOKS / name)], input=json.dumps(event),
        text=True, capture_output=True, cwd=cwd, env=env, timeout=timeout,
    )
    if result.returncode:
        raise RuntimeError(f"{name}: {result.stderr.strip() or result.returncode}")
    if not result.stdout.strip():
        return None
    if name == "session_context.sh":
        return {"hookSpecificOutput": {
            "hookEventName": "SessionStart", "additionalContext": result.stdout,
        }}
    return json.loads(result.stdout)


def patch_paths(command):
    return re.findall(r"^\*\*\* (?:Add File|Update File|Delete File|Move to): (.+)$",
                      command, re.MULTILINE)


def denied(output):
    return bool(output and (
        output.get("decision") == "block" or
        output.get("hookSpecificOutput", {}).get("permissionDecision") == "deny"
    ))


def dispatch(event):
    kind = event["hook_event_name"]
    cwd = Path(event["cwd"])
    data = event.get("tool_input") or {}
    name = event.get("tool_name", "")
    # Codex currently normalizes exec_command to Bash/command; tolerate raw
    # names too so recorded events can be replayed in regression tests.
    if name in ("Bash", "exec_command"):
        cwd = (cwd / (data.get("workdir") or data.get("cwd") or ".")).resolve()
        event = {**event, "cwd": str(cwd), "tool_name": "Bash", "tool_input": {
            **data, "command": data.get("command", data.get("cmd", "")),
        }}
        name = "Bash"
    if kind == "SessionStart":
        return run("session_context.sh", event, cwd, 12)
    if kind == "PreToolUse":
        if name == "apply_patch":
            command = data.get("command", data.get("input", ""))
            for path in patch_paths(command):
                output = run("guard.py", {**event, "tool_name": "Write",
                             "tool_input": {"file_path": path}}, cwd)
                if denied(output):
                    return output
            return None
        output = run("guard.py", event, cwd)
        if denied(output):
            return output
        if name == "Bash":
            return run("review_gate.py", event, cwd)
    if kind == "PostToolUse" and name in ("apply_patch", "Write", "Edit", "MultiEdit"):
        paths = patch_paths(data.get("command", data.get("input", ""))) if name == "apply_patch" else [data.get("file_path", "")]
        messages = []
        for path in paths:
            path = str((cwd / path).resolve())
            output = run("ruff_touched_file.sh", {**event, "tool_input": {"file_path": path}}, cwd)
            if output:
                messages.append(output.get("reason") or output.get("systemMessage", ""))
        if messages:
            return {"decision": "block", "reason": "\n".join(messages)}
    if kind == "Stop":
        return run("stop_tests.py", event, cwd, 290)
    if kind == "SubagentStop":
        agent = event.get("agent_type", "").split(":")[-1]
        # Do not parse Codex transcripts as Claude transcripts, or record a
        # test engineer's Ready verdict as an independent code review.
        if agent == "noemeo-code-reviewer":
            message = event.get("last_assistant_message") or ""
            if not message.strip():
                return {"systemMessage": "Noemeo: reviewer report absent; approval not recorded."}
            return run("review_record.py", {**event,
                "agent_transcript_path": None, "transcript_path": None}, cwd)
    return None


def main():
    event = {}
    try:
        event = json.load(sys.stdin)
        output = dispatch(event)
        if output:
            print(json.dumps(output))
    except Exception as error:
        # Explicit denial is required: a failed Codex hook may fail open.
        reason = f"Noemeo hook could not verify policy: {error}"
        kind = event.get("hook_event_name")
        if kind == "PreToolUse":
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": kind, "permissionDecision": "deny",
                "permissionDecisionReason": reason,
            }}))
        elif kind in ("Stop", "PostToolUse"):
            print(json.dumps({"decision": "block", "reason": reason}))
        else:
            print(json.dumps({"systemMessage": reason}))


if __name__ == "__main__":
    main()
