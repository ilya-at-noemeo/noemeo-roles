"""The hooks' minimum Python, checked before anything that needs it.

Hooks run with the first `python3` on the PATH Claude Code (or Codex)
starts them with. An older one would crash at import, which the harness
treats as a non-blocking error: a guard would be silently off. Each entry
point calls `check` first, so an old Python fails loudly instead.

This file must stay importable on old Pythons: no `X | Y` annotations,
walrus, `match` or f-string `=`.
"""

import json
import sys

MIN = (3, 12)


def message(name):
    found = ".".join(str(n) for n in tuple(sys.version_info)[:3])
    return (
        "{} needs Python {}.{} or newer; found {} at {}. "
        "Put a newer python3 first on the PATH Claude Code runs hooks with "
        "(docs/hooks.md).".format(name, MIN[0], MIN[1], found, sys.executable)
    )


def check(fail, name, event=None):
    """Return on a new enough Python; otherwise fail as `fail` says.

    closed: the sentence on stderr, exit 2 (blocks a tool call).
    open: {"systemMessage": sentence} on stdout, exit 0.
    text: the sentence as plain text on stdout, exit 0.
    context: hookSpecificOutput.additionalContext for hook `event`, exit 0.
    """
    if tuple(sys.version_info)[:2] >= MIN:
        return
    text = message(name)
    if fail == "closed":
        sys.stderr.write(text + "\n")
        sys.exit(2)
    if fail == "open":
        print(json.dumps({"systemMessage": text}))
    elif fail == "context":
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": event, "additionalContext": text,
        }}))
    else:
        print(text)
    sys.exit(0)
