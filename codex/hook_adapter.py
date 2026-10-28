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


def project_dir(cwd):
    """The Git checkout cwd is in, where its .claude/ policy lives; else cwd."""
    result = subprocess.run(["git", "-C", str(cwd), "rev-parse", "--show-toplevel"],
                            capture_output=True, text=True)
    return result.stdout.strip() if result.returncode == 0 else str(cwd)


def run(name, event, cwd, project, timeout=30):
    # Hooks read the repo's policy from CLAUDE_PROJECT_DIR, which Claude
    # fixes at the session's project root. It comes from the session's
    # directory, never from a workdir the model picks; the command's own
    # directory stays cwd.
    env = dict(os.environ, CLAUDE_PROJECT_DIR=project, PYTHONDONTWRITEBYTECODE="1")
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


def guard(event, cwd, projects):
    """The first denial from the guard under each project's policy, if any."""
    for project in projects:
        output = run("guard.py", event, cwd, project)
        if denied(output):
            return output
    return None


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
    project = project_dir(cwd)
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
        return run("session_context.sh", event, cwd, project, 12)
    if kind == "PreToolUse":
        # The session's policy always applies; a command run in another
        # checkout must also pass that checkout's own.
        projects = list(dict.fromkeys([project, project_dir(cwd)]))
        if name == "apply_patch":
            command = data.get("command", data.get("input", ""))
            for path in patch_paths(command):
                output = guard({**event, "tool_name": "Write",
                               "tool_input": {"file_path": path}}, cwd, projects)
                if denied(output):
                    return output
            return None
        output = guard(event, cwd, projects)
        if denied(output):
            return output
        if name == "Bash":
            return run("review_gate.py", event, cwd, project)
    if kind == "PostToolUse" and name in ("apply_patch", "Write", "Edit", "MultiEdit"):
        paths = patch_paths(data.get("command", data.get("input", ""))) if name == "apply_patch" else [data.get("file_path", "")]
        messages = []
        for path in paths:
            path = str((cwd / path).resolve())
            output = run("ruff_touched_file.sh", {**event, "tool_input": {"file_path": path}}, cwd, project)
            if output:
                messages.append(output.get("reason") or output.get("systemMessage", ""))
        if messages:
            return {"decision": "block", "reason": "\n".join(messages)}
    if kind == "Stop":
        return run("stop_tests.py", event, cwd, project, 290)
    if kind == "SubagentStop":
        agent = event.get("agent_type", "").split(":")[-1]
        # Do not parse Codex transcripts as Claude transcripts, or record a
        # test engineer's Ready verdict as an independent code review.
        if agent == "noemeo-code-reviewer":
            message = event.get("last_assistant_message") or ""
            if not message.strip():
                return {"systemMessage": "Noemeo: reviewer report absent; approval not recorded."}
            return run("review_record.py", {**event,
                "agent_transcript_path": None, "transcript_path": None}, cwd, project)
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
