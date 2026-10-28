# Noemeo for Codex

Codex fills the same Noemeo roles as Claude Code, from the same files.
They are the source of truth; never write Codex versions of them. This
file only translates. Paths below are relative to this checkout of
noemeo-roles (the parent of this file's directory).

## Load

1. `roles/working-agreement.md`, before any task. The session-start
   hook also prints it; read the file if that output is missing.
2. The repo's rules, as the agreement's "Sources" says.
3. The role for the work:
   - Vision: `roles/product/vision.md`.
   - Planning: `roles/product/product-management.md`.
   - UX: `roles/product/ux-design.md`.
   - Architecture: `roles/engineering/architecture.md`.
   - AI, prompts, evaluation, ML: `roles/engineering/ai-engineering.md`.
   - Implementation: `roles/engineering/implementation.md`.
   - Test building and independent review: `roles/engineering/testing.md`.
   - Research: `roles/research/research.md`.
4. The skill that carries it out: `skills/<name>/SKILL.md`. There is no
   Skill tool; reading and following that file is the equivalent.
   Resolve its relative paths from its own directory, even when it was
   found through `.agents/skills`.

An end-to-end change follows `skills/noemeo-ship/SKILL.md`, up to the
endpoint the user asked for. It is not permission to publish.

## Translate

- Claude tool names (Read, Edit, Bash, Skill, SendMessage) name
  operations; use Codex's equivalents.
- Claude model names and tool allowlists are not Codex settings:
  inherit the session's model and permissions, and keep the role's hard
  limits as instructions.
- "Spawn `<agent>`" means the custom agent of that name in
  `.codex/agents/`, which loads `agents/<agent>.md`. Give the reviewer
  the target, intended behaviour and constraints, never your reasoning
  or history. If named custom agents are unavailable, use a fresh agent
  told to read the same definition, and report that the review can't be
  recorded, so the PR gate will refuse it.
- Codex doesn't load `.claude/settings.json`. When AWS is involved, use
  the profile the repo's `CLAUDE.md` names; from `.claude/settings.json`
  read only its `AWS_PROFILE` entry, and never dump environment values.

## Enforcement

The hooks in `.codex/hooks.json` run the same guard, review gate,
review record, ruff and test scripts as Claude Code, through
`codex/hook_adapter.py`, with the repo's `.claude/noemeo-guard.json`.
They act only once this session has loaded and the user has trusted
them; don't claim enforcement before that. Open PRs only with `gh`, the
command the gate checks, never through a connector or another API.
Agent usage isn't logged under Codex.
