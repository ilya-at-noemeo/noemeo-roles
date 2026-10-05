#!/usr/bin/env bash
# PostToolUse (Write|Edit): ruff check --fix, then ruff format, on the
# Python file Claude just wrote -- only in a repo that has opted in:
# its pyproject.toml has a [tool.ruff] table and ruff is installed in
# its .venv. Lint errors --fix can't resolve go back to Claude as
# feedback; formatting is just applied.
set -u

file=$(jq -r '.tool_input.file_path // .tool_response.filePath // empty')
case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

# The file's own repo, which needn't be the session's.
root=$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null) || exit 0
grep -q '^\[tool\.ruff\]' "$root/pyproject.toml" 2>/dev/null || exit 0
ruff="$root/.venv/bin/ruff"
[ -x "$ruff" ] || exit 0
cd "$root" || exit 0

# Fix first, then format: a removed import can leave layout that only
# format cleans up. --force-exclude honours the repo's excludes even for
# a file named explicitly.
out=$("$ruff" check --force-exclude --fix --output-format concise --quiet "$file" 2>&1)
status=$?
"$ruff" format --force-exclude --quiet "$file" >/dev/null 2>&1
if [ $status -ne 0 ] && [ -n "$out" ]; then
  jq -n --arg out "$out" \
    '{decision: "block", reason: ("ruff check found problems --fix could not resolve:\n" + $out)}'
fi
exit 0
