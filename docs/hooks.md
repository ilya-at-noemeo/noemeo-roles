# Hooks

The same plugin ships hooks (`hooks/hooks.json`), so they run in every
repo it's enabled in. Guarantees, not suggestions: each runs on its
lifecycle event whatever the model decides.

| Event | Hook | Does |
| --- | --- | --- |
| PreToolUse | `guard.py` | Denies `rm -rf`, force-pushes, `git clean -f`, and Bash or file-tool access to secrets: `.env`/`.env.*` (not `.env.example`), `*.pem`, `.certs/`, `.aws/credentials`. Commit messages and PR bodies that only mention them are allowed. In a repo that lists its AWS profiles, also denies `aws`/`terraform` commands that don't use one. |
| SessionStart | `session_context.sh` | Adds branch, uncommitted files, recent commits, open GitHub issues, the last failing test run and `roles/working-agreement.md` to the session. |
| PreToolUse | `review_gate.py` | Before `gh pr create` (or its alias `gh pr new`), denies unless `noemeo-code-reviewer`'s latest review of the change *as it is now* says Ready or Ready with nits; tells Claude to run the reviewer otherwise. Fails closed: a mention counts unless it sits wholly in a heredoc body or quoted string, the command runs no shell, interpreter or other runner (`sh -c`, `python`, `xargs`, `ssh`, `$VAR`, ...) and no `$(`/backtick comes before it -- so a commit message naming it passes, anything else is denied. |
| SubagentStop | `review_record.py` | When `noemeo-code-reviewer` finishes, records its verdict against a fingerprint of the repo it names: the content of every file changed since the merge-base with the PR base, untracked files included. It records against the repo's default bases (`origin/HEAD`, `origin/dev`, `origin/main`) and any remote branch the branch is stacked on (in its history, not yet in a default base), so a PR targeting another open branch can pass the gate. A stacked base that has gained commits since isn't in the branch's history: rebase onto it, then review. Committing reviewed changes keeps the fingerprint; any further edit voids it. Records live in the repo's git directory (`noemeo-reviews.jsonl`), never in the tree. Its matcher is the regex `(^\|:)noemeo-code-reviewer$`: a plugin agent's type is scoped (`noemeo:noemeo-code-reviewer`), and a matcher of only letters and hyphens is compared exactly, so the plain name never fires. |
| PostToolUse | `ruff_touched_file.sh` | `ruff check --fix` then `ruff format` on each edited `.py` file; unfixable lint goes back to Claude. |
| Stop | `stop_tests.py` | `pytest -x -q` plus the repo's `stop_pytest_args`; a failure blocks the turn from ending and is handed back. Skipped when the tree is unchanged since the last green run. |
| SubagentStop | `agent_usage.py` | For every subagent, appends one JSON line to `~/.claude/noemeo-agent-usage.jsonl` (or `$NOEMEO_AGENT_USAGE_LOG`): agent type and task, repo, model, input and cache tokens, characters written, tool calls and duration, read from the subagent's own transcript. Output tokens aren't logged: the transcript usually keeps a streamed message's usage from the start of the stream, so its output counts are mostly near zero. A resumed agent logs its running total, so the last line per agent id is its total. Never blocks. |

A repo opts in to the last two by having what they need, nothing else:

- **ruff:** a `[tool.ruff]` table in its `pyproject.toml` and ruff in its
  `.venv` (a dev dependency). Without both, edits aren't touched -- so
  adopting it is a deliberate one-time format commit, not drift.
- **tests:** pytest in its `.venv`.

A linked worktree without the tool in its `.venv` while its main
checkout has it (a fresh, uninstalled worktree) gets a one-line warning
once per session rather than a silent skip; `noemeo-worktree` makes
worktrees with their dependencies installed.

A repo can add pytest arguments for the Stop hook in
`.claude/noemeo-guard.json`, e.g. to leave slow browser tests to review
and CI:

```json
{ "stop_pytest_args": ["-m", "not browser"] }
```

A repo with secrets of its own lists them in `.claude/noemeo-guard.json`,
as literal names or `*.<ext>`:

```json
{ "secrets": [".my_tokens.json", "*.p12"] }
```

A repo that works against an AWS account names that account's profiles
from `~/.aws/config` there too. The guard then denies an `aws` or
`terraform` command that can reach AWS unless it uses one of them
(`--profile`, an `AWS_PROFILE=` prefix, or `AWS_PROFILE` in the
session), so nothing falls back to the default credentials, which on a
developer's own machine may be another account. Pair it with
`"env": {"AWS_PROFILE": "<profile>"}` in the repo's
`.claude/settings.json`, so scripts and SDKs default to the right
account too. That env is the real protection: the guard reads command
text, so it can't see AWS calls made inside a script, `bash -c`, an
`npm run` script or an SDK. A command that unsets or overrides
`AWS_PROFILE` itself must name a listed profile on each `aws` or
`terraform` it runs:

```json
{ "aws_profiles": ["acme-dev", "acme-admin"] }
```

The guard reads command text, not intent, so it errs toward denying:
a heredoc that feeds a script and merely *mentions* a blocked command
or secret is denied too. Write such text with the file tools instead.

Tool-specific hooks for other stacks (`terraform fmt`, say) get added
here once a repo actually needs one. Review or disable
hooks with `/hooks`.
