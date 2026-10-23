---
name: noemeo-worktree
description: Creates and removes parallel git worktrees of a Noemeo repo that are ready to work in -- outside every repo so no stale CLAUDE.md is loaded, with .env copied and dependencies installed into .venv so the plugin's ruff and test hooks run. Use when asked for a worktree, a parallel checkout or a second copy of a repo to work on another branch, and to clean one up after its branch merges.
---

# Worktrees

Use `${CLAUDE_SKILL_DIR}/scripts/noemeo-worktree` instead of a bare
`git worktree add`, which leaves a checkout with no `.venv`: the plugin's
ruff and Stop-test hooks then don't run there.

From anywhere inside the repo:

```bash
"${CLAUDE_SKILL_DIR}/scripts/noemeo-worktree" add <branch> [<base>]
"${CLAUDE_SKILL_DIR}/scripts/noemeo-worktree" remove <branch>
"${CLAUDE_SKILL_DIR}/scripts/noemeo-worktree" list
```

- `add` fetches, branches from `origin/HEAD` (or `<base>`), creates the
  worktree in `.worktrees/<repo>/<branch>` beside the main checkout
  (`$NOEMEO_WORKTREES_DIR` overrides), copies `.env`/`.env.*` and runs
  `poetry install` or `uv sync`. An existing local branch is checked out
  instead, and a branch that exists only on `origin` is checked out
  tracking it.
- Not inside the main checkout: Claude Code loads every `CLAUDE.md` above
  the working directory, so a nested worktree would get main's rules on
  top of its branch's.
- Work in it from a **new Claude session started in the worktree**, and
  tell the user so with the printed path. The current session keeps its
  project directory: its `CLAUDE.md` stays main's and the Stop hook keeps
  testing main's tree, not the worktree's edits.
- `remove` refuses while the worktree has modified or untracked files,
  and deletes the branch only if it's merged. Report the "kept branch"
  message to the user rather than forcing either.
- A worktree branches from current `origin/HEAD`, so its `CLAUDE.md` is
  current when made. One kept for days goes stale: merge the base in
  before long work there.
