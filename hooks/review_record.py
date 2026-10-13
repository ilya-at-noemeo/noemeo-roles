#!/usr/bin/env python3
"""SubagentStop hook for noemeo-code-reviewer: record its verdict against
a fingerprint of each repo it names (review_state.py), so review_gate.py
can tell whether the change about to become a PR was reviewed as it is.

The reviewer's report opens with a verdict line naming the repo by
absolute path; every existing git repo path in that report is recorded,
falling back to the session's working directory. Never blocks.
"""

import json
import re
import sys
from pathlib import Path

sys.dont_write_bytecode = True  # no __pycache__ beside the hooks
sys.path.insert(0, str(Path(__file__).parent))
from review_state import record, toplevel  # noqa: E402

VERDICTS = ("Not ready", "Ready with nits", "Ready")


def main() -> None:
    event = json.load(sys.stdin)
    message = event.get("last_assistant_message") or ""
    verdict = next((v for v in VERDICTS if v in message[:400]), None)
    if verdict is None:
        return  # not a finished review (asked a question, or failed)
    repos = []
    for candidate in re.findall(r"(/[\w.@~+-]+(?:/[\w.@~+-]+)+)", message):
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
