#!/usr/bin/env bash
# PostToolUse (Write|Edit): ruff check --fix, then ruff format, on the
# Python file Claude just wrote -- only in a repo that has opted in:
# its pyproject.toml has a [tool.ruff] table and ruff is installed in
# its .venv. Lint errors --fix can't resolve go back to Claude as
# feedback; formatting is just applied. A linked worktree without
# .venv/bin/ruff whose main checkout has one (a fresh worktree nobody
# installed) gets a one-line warning, once per session, instead of a
# silent skip.
set -u

input=$(cat)
file=$(jq -r '.tool_input.file_path // .tool_response.filePath // empty' <<<"$input")
case "$file" in
  *.py) ;;
  *) exit 0 ;;
esac
[ -f "$file" ] || exit 0

# The file's own repo, which needn't be the session's.
root=$(git -C "$(dirname "$file")" rev-parse --show-toplevel 2>/dev/null) || exit 0
grep -q '^\[tool\.ruff\]' "$root/pyproject.toml" 2>/dev/null || exit 0
ruff="$root/.venv/bin/ruff"
if [ ! -x "$ruff" ]; then
  main=$(dirname "$(git -C "$root" rev-parse --path-format=absolute --git-common-dir 2>/dev/null)")
  { [ "$main" != "$root" ] && [ -x "$main/.venv/bin/ruff" ]; } || exit 0
  session=$(jq -r '.session_id // empty' <<<"$input")
  marker="$(git -C "$root" rev-parse --absolute-git-dir 2>/dev/null)/claude-ruff-skip-warned"
  if [ -z "$session" ] || [ "$(cat "$marker" 2>/dev/null)" != "$session" ]; then
    { printf '%s' "$session" >"$marker"; } 2>/dev/null
    jq -n --arg root "$root" \
      '{systemMessage: ("ruff hook: no .venv/bin/ruff in " + $root + " (its main checkout has one), so edits there are not linted. Install its dev dependencies.")}'
  fi
  exit 0
fi
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
