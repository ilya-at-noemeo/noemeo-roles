#!/usr/bin/env bash
# SessionStart: prints branch, working-tree state, recent commits, open
# GitHub issues, the last failing test run (from stop_tests.py) and the
# working agreement (roles/working-agreement.md) --
# stdout becomes context for the session. Every part is best-effort, and
# outside a git repo it prints nothing.
set -u
here=$(cd "$(dirname "$0")" && pwd)
cd "${CLAUDE_PROJECT_DIR:-.}" 2>/dev/null || exit 0
git rev-parse --git-dir >/dev/null 2>&1 || exit 0  # not a git repo

echo "## Repo state at session start"
echo
branch=$(git branch --show-current 2>/dev/null)
upstream=$(git rev-list --left-right --count '@{upstream}...HEAD' 2>/dev/null | awk '{print "behind " $1 ", ahead " $2}')
echo "Branch: ${branch:-detached} ${upstream:+($upstream of upstream)}"

changes=$(git status --short 2>/dev/null)
if [ -n "$changes" ]; then
  echo "Uncommitted changes ($(printf '%s\n' "$changes" | wc -l | tr -d ' ') files):"
  printf '%s\n' "$changes" | head -20
else
  echo "Working tree clean."
fi

echo
echo "Recent commits:"
git log --oneline -5 2>/dev/null

if command -v gh >/dev/null 2>&1; then
  # timeout is GNU coreutils (Homebrew on macOS) -- without it, run gh
  # unbounded rather than skipping it.
  t=$(command -v timeout || command -v gtimeout)
  issues=$(${t:+$t 5} gh issue list --state open --limit 10 2>/dev/null)
  if [ -n "$issues" ]; then
    echo
    echo "Open GitHub issues:"
    printf '%s\n' "$issues"
  fi
fi

failure="$(git rev-parse --absolute-git-dir 2>/dev/null)/claude-tests-last-failure"
if [ -s "$failure" ]; then
  echo
  echo "Last test run FAILED (as of $(date -r "$failure" '+%Y-%m-%d %H:%M')); tail:"
  tail -25 "$failure"
fi

# The rules every role follows, from this copy of noemeo-roles, so
# every main session starts with them whichever tool runs it.
agreement="$here/../roles/working-agreement.md"
if [ -s "$agreement" ]; then
  echo
  echo "## Noemeo working agreement (noemeo-roles roles/working-agreement.md)"
  echo
  sed '1,/^$/d' "$agreement"  # drop its title line
fi
exit 0
