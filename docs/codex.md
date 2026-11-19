# Codex alongside Claude Code

The role definitions, `roles/working-agreement.md`, skills, foundation,
decisions, `CLAUDE.md` files and `.claude/noemeo-guard.json` remain the
shared sources of truth. Codex reads them directly; `codex/AGENTS.md`
only translates Claude's terms. Claude's plugin wiring and settings
are unchanged.

Install or update from the noemeo-roles checkout:

```bash
python3 codex/install.py /absolute/path/to/repo [...]
python3 codex/install.py --check /absolute/path/to/repo [...]
```

The installer writes a short `AGENTS.md`, one `.agents/skills/<name>`
link per skill (this repo's skills plus the target repo's own, found in
its `.claude/skills/`), seven `.codex/agents/*.toml` profiles,
`.codex/hooks.json` and a project config enabling hooks. These files
hold this machine's absolute paths, so they are local, never committed:
the installer lists each one in Git's `info/exclude` (shared by the
main checkout and its linked worktrees) and records each one's hash in
`.codex/noemeo-install.json`.

Rerun it after changing an agent, a skill or this repo's location: it
replaces its own files while they're unchanged since it wrote them, and
removes those no longer generated. Anything else in the way -- a file
it didn't write, one edited since, or two skills with the same name --
is a conflict, and a conflict anywhere aborts every write. Generated
files are never edited by hand; change the source and rerun.

`--check` writes nothing and exits 1 on any drift: a generated file
missing, stale or edited, Claude's installed copy of the plugin
differing from this checkout (fix with `claude plugin update`), or a
Codex plugin cache holding a copy of a linked skill that differs from
its source. The plugin copy check matters because Claude runs a copy,
while Codex reads this checkout live: an edit here reaches Codex at
once and Claude only after an update.

A linked worktree is a separate checkout: install there too. Linked
worktrees share one `info/exclude`; each checkout's paths sit in their
own block, headed with that checkout's path.

The folder holding the checkouts (the parent of noemeo-roles) may also
be a target, though it isn't a Git checkout, so a Codex session started
there gets the same instructions. Nothing is excluded there, and the
session-start hook prints nothing outside a Git checkout: there,
`AGENTS.md` alone points at the working agreement.

Every check runs before the first write, but a disk error midway can
still leave a run partial; rerun to finish it.

Start a fresh Codex session in the target checkout. Review and trust the
project and exact hook definitions using Codex's hook review UI (`/hooks`
in the CLI). No trust entries, bypass switches, global settings, or sandbox
permissions are changed by the installer. Hook trust is a user action.

The adapter delegates to the same guard, review fingerprint/record/gate,
session-context, ruff and Stop-test implementations Claude uses. It handles
Codex's patch tool and normalizes shell arguments. Only a named
`noemeo-code-reviewer` SubagentStop event with an actual final report can
record a review. Claude and Codex use the same Git review records, so
switching tools does not inherently discard a matching approval; edits do.

Custom profiles inherit the session model and permissions. Claude's Sonnet
preferences are not translated to a different model. Read-only and test-only
limits remain role instructions, rather than separate sandbox policies.
If a client exposes only generic delegation, load the shared agent Markdown
in a fresh context, report that automatic review recording is unavailable,
and do not fabricate records or bypass the PR gate.

Codex transcript usage accounting is not implemented: Claude's agent-usage
logger depends on Claude's transcript format and is not run on Codex events.
Do not claim identical token accounting across tools.

Before relying on enforcement, verify in a fresh trusted session:

1. Ask it to list its instruction sources and available Noemeo agents.
2. Confirm a harmless attempted read of a dummy `.env` path is denied.
3. In a disposable repository, confirm PR creation without approval is
   denied before any network call; a named reviewer records its verdict.
4. Confirm a later file edit invalidates approval.
5. In an opted-in fixture, confirm patch edits run ruff and a failing test
   causes a Stop continuation.

## Decisions

The adapter runs `hooks/decision_delivery.py` on PreToolUse after the
guard and before the review gate: a binding decision in scope denies
the first shell command or edit once, with its text, and the retry
passes. `apply_patch` is checked once per patched path as a `Write`; the
first denial is returned. A guard denial returns before delivery runs,
so it doesn't use up a delivery. On PostToolUse after `apply_patch`,
`Write`, `Edit` and `MultiEdit`, decision feedback is merged with
ruff's messages into one block reason. A delivery failure prints a
system message and never denies.

Gaps:

- Codex has no Read tool. Files read through the shell get no
  descriptive (post-read) delivery; only binding decisions scoped to a
  command or an edit reach the model.
- Whether Codex events carry an agent id is unconfirmed. If they don't,
  subagents share the session's delivery state, so a decision delivered
  to the main agent isn't repeated to a subagent.
- Pending manual check, run by the owner in a real Codex session:
  `python3 codex/install.py /path/to/disposable-repo` in a repo with
  one binding decision (`paths: ["src/**"]`) and `decision_roots`
  in `.claude/noemeo-guard.json`; trust the hooks in `/hooks`; start a
  fresh session and ask for an `apply_patch` edit under `src/`. Expect
  the first to be refused with the decision's text and the retry to go
  through; also check whether the event carries an agent id. Result:
  not yet run.

Adapter regression tests exercise recorded/synthetic events locally. They
do not establish that the desktop runtime has loaded or trusted hooks.
Current source documentation:

- https://learn.chatgpt.com/docs/agent-configuration/agents-md
- https://learn.chatgpt.com/docs/agent-configuration/subagents
- https://learn.chatgpt.com/docs/hooks

Switching tools does not transfer private chat history; the working
agreement's "Picking up and handing off" covers resuming from the
actual branch and leaving a handoff.
