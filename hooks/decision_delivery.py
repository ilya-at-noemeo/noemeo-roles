#!/usr/bin/env python3
"""Delivers decisions on tool calls, in every repo that configures
`decision_roots` in .claude/noemeo-guard.json.

- PreToolUse (Bash and the edit tools): a binding decision in scope that
  this context hasn't had with its current content denies the action once,
  with the decision's text. The retry passes.
- PostToolUse (Read and the edit tools): every decision in scope not yet
  delivered arrives as feedback ({"decision": "block", "reason": ...}).
  A read is never blocked: the feedback comes after it, and binding
  decisions delivered that way count as delivered.

State: `noemeo-decisions-delivered.json` in the Git dir,
`{context_key: {decision_id: content_hash}}`, where the key is the session id,
plus `/agent_id` inside a subagent. A corrupt state file counts as empty,
so decisions are delivered again rather than skipped.

This runs on every tool call, so it exits at once when nothing applies and
never blocks a call because of its own failure: an internal error prints
a systemMessage naming `decisions.py lint` and allows the call.

A PreToolUse call that guard.py denies isn't the action that will run,
so delivery runs the guard on the same event first and, on a deny,
neither records nor denies (the guard's own hook denies it). A guard
that fails, times out or prints nothing never holds delivery back.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import pyfloor  # noqa: E402

pyfloor.check("open", "decision_delivery.py")  # before anything that needs 3.12

STATE = "noemeo-decisions-delivered.json"
CONFIG = Path(".claude") / "noemeo-guard.json"
PRE_TOOLS = ("Bash", "Edit", "Write", "MultiEdit", "NotebookEdit")
POST_TOOLS = ("Read", "Edit", "Write", "MultiEdit", "NotebookEdit")
PER_DECISION_CAP = 4000
TOTAL_CAP = 12000
CLOSING = "Delivered once. Retry the action if it complies; otherwise change it."
GUARD = Path(__file__).resolve().parent / "guard.py"
GUARD_TIMEOUT = 5


def context_key(event: dict) -> str:
    key = str(event.get("session_id") or "nosession")
    agent = event.get("agent_id")
    return f"{key}/{agent}" if agent else key


def find_git_dir(project: Path) -> Path | None:
    """The Git dir of the repo holding `project`, without running Git."""
    for candidate in (project, *project.parents):
        dot = candidate / ".git"
        try:
            if dot.is_dir():
                return dot
            if dot.is_file():
                text = dot.read_text(encoding="utf-8", errors="replace")
                if text.startswith("gitdir:"):
                    target = Path(text[len("gitdir:"):].strip())
                    return target if target.is_absolute() else candidate / target
        except OSError:
            return None
    return None


def read_state(git_dir: Path) -> dict:
    """Missing or corrupt state is empty; an unreadable file is an error."""
    try:
        raw = (git_dir / STATE).read_bytes()
    except FileNotFoundError:
        return {}
    try:
        loaded = json.loads(raw.decode("utf-8"))
    except ValueError:  # includes bad UTF-8
        return {}
    if not isinstance(loaded, dict):
        return {}
    clean = {}
    for key, delivered in loaded.items():
        if isinstance(delivered, dict):
            clean[str(key)] = {
                str(i): v for i, v in delivered.items() if isinstance(v, str)
            }
    return clean


def write_state(git_dir: Path, state: dict) -> None:
    tmp = git_dir / f"{STATE}.{os.getpid()}.tmp"
    try:
        tmp.write_text(json.dumps(state, sort_keys=True), encoding="utf-8")
        os.replace(tmp, git_dir / STATE)
    except BaseException:
        try:
            tmp.unlink()
        except OSError:
            pass
        raise


def record(git_dir: Path, key: str, delivered: dict) -> None:
    """Merge into the freshest state, so another context's entries stay."""
    state = read_state(git_dir)
    state.setdefault(key, {}).update(delivered)
    write_state(git_dir, state)


def reset_session(git_dir: Path, session_id: str) -> None:
    """Forget what a session (and its subagents) was shown."""
    state = read_state(git_dir)
    kept = {
        k: v
        for k, v in state.items()
        if k != session_id and not k.startswith(session_id + "/")
    }
    if kept != state:
        write_state(git_dir, kept)


def _unit(corpus, d) -> list:
    """A decision followed by its current amendments, all the way down."""
    from decisions import amendments_of

    out, seen = [], set()

    def add(x):
        if id(x) in seen:
            return
        seen.add(id(x))
        out.append(x)
        for a in amendments_of(corpus, x):
            add(a)

    add(d)
    return out


def units(corpus, resolved: list) -> list[list]:
    """Group resolved decisions into originals with their amendments."""
    covered: set[int] = set()
    grouped = []
    for d in resolved:
        if id(d) in covered:
            continue
        unit = _unit(corpus, d)
        covered.update(id(x) for x in unit)
        grouped.append(unit)
    return grouped


def _path_of(d, corpus) -> str:
    try:
        return Path(os.path.relpath(d.source, corpus.project)).as_posix()
    except (ValueError, TypeError):
        return str(d.source)


def render_delivery(decisions: list, corpus) -> str:
    """Id and delivered text of each decision, its current amendments
    labelled `Amended by <id>:`. Each text is cut at 4000 characters and
    the texts together at 12000; whatever is cut or left out is named with
    its path."""
    blocks: list[tuple[object, str, str]] = []  # (decision, heading, text)
    for unit in units(corpus, decisions):
        for n, d in enumerate(unit):
            heading = d.id if n == 0 else f"Amended by {d.id}:"
            blocks.append((d, heading, d.text))
    remaining = TOTAL_CAP
    parts, cut = [], []
    for d, heading, text in blocks:
        room = min(PER_DECISION_CAP, remaining)
        if room <= 0:
            cut.append(d)
            parts.append(heading)
            continue
        shown = text[:room]
        remaining -= len(shown)
        if len(shown) < len(text):
            cut.append(d)
            shown += "\n[cut]"
        parts.append(f"{heading}\n{shown}")
    out = "\n\n".join(parts)
    if cut:
        listed = "\n".join(f"- {d.id}: {_path_of(d, corpus)}" for d in cut)
        out += f"\n\nNot shown in full; read these files:\n{listed}"
    return out


def target(event: dict) -> tuple[list[Path], list[str]]:
    """(paths, commands) the tool call touches."""
    tool_input = event.get("tool_input")
    if not isinstance(tool_input, dict):
        return [], []
    if event.get("tool_name") == "Bash":
        command = tool_input.get("command")
        return [], [command] if isinstance(command, str) else []
    raw = tool_input.get("file_path") or tool_input.get("notebook_path")
    if not isinstance(raw, str) or not raw:
        return [], []
    path = Path(raw)
    if not path.is_absolute():
        path = Path(event.get("cwd") or os.getcwd()) / path
    return [path], []


def guard_denies(event: dict) -> bool:
    """True only when guard.py clearly denies this event."""
    try:
        done = subprocess.run(
            [sys.executable, str(GUARD)],
            input=json.dumps(event),
            capture_output=True,
            text=True,
            timeout=GUARD_TIMEOUT,
        )
        out = json.loads(done.stdout) if done.stdout.strip() else None
    except Exception:  # noqa: BLE001 - a guard problem never holds delivery back
        return False
    if not isinstance(out, dict):
        return False
    specific = out.get("hookSpecificOutput")
    return isinstance(specific, dict) and specific.get("permissionDecision") == "deny"


def decide(event: dict) -> dict | None:
    name = event.get("hook_event_name")
    tool = event.get("tool_name")
    if name == "PreToolUse" and tool in PRE_TOOLS:
        pre = True
    elif name == "PostToolUse" and tool in POST_TOOLS:
        pre = False
    else:
        return None
    project = Path(os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd())
    if not (project / CONFIG).is_file():
        return None
    git_dir = find_git_dir(project)
    if git_dir is None:
        return None
    paths, commands = target(event)
    if not paths and not commands:
        return None

    import decisions

    corpus = decisions.load(project)
    resolved = decisions.resolve(corpus, paths=paths, commands=commands)
    if not resolved:
        return None
    key = context_key(event)
    delivered = read_state(git_dir).get(key, {})
    pending = []
    for unit in units(corpus, resolved):
        if all(delivered.get(d.id) == d.content_hash for d in unit):
            continue
        if pre and not any(d.binding for d in unit):
            continue
        pending.extend(unit)
    if not pending:
        return None
    if pre and guard_denies(event):
        return None  # not the action that will run; deliver on the next one
    text = render_delivery(pending, corpus)
    record(git_dir, key, {d.id: d.content_hash for d in pending})  # before any deny
    if pre:
        return {
            "hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": f"{text}\n\n{CLOSING}",
            }
        }
    return {"decision": "block", "reason": text}


def main() -> None:
    try:
        event = json.load(sys.stdin)
        if not isinstance(event, dict):
            return
    except ValueError:
        return
    try:
        out = decide(event)
    except Exception as e:  # noqa: BLE001 - never block a call for our own failure
        out = {
            "systemMessage": (
                f"Decision delivery failed ({e!r}); the action was not blocked. "
                "Run decisions.py lint to find the cause."
            )
        }
    if out:
        print(json.dumps(out))


if __name__ == "__main__":
    main()
