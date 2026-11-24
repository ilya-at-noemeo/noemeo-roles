---
name: noemeo-brief
description: Writes or updates a task's brief -- the worktree's CLAUDE.local.md, which Claude Code loads at launch, re-reads after compaction and gives to subagents -- from an approved operational spec or, without one, from the developer's request, kept out of Git. Use when the developer asks for a brief, a CLAUDE.local.md or "the requirements for this session", when starting work on a task that has a spec, when the ship skill offers one, or when the task's requirements change mid-task.
---

# Task brief

The brief tells the agents working on one task what that task must
deliver. It lives in `CLAUDE.local.md` at the worktree's root: Claude
Code loads it at launch, re-reads it from disk after compaction, and
general-purpose and custom subagents load it too (Explore doesn't). It
is the developer's file: they review and correct it, and you update it
when they ask or when the task's understanding changes.

How to work in the repo is `CLAUDE.md`'s job; the brief holds only the
sections below.

## 1. Find the place

- `root=$(git rev-parse --show-toplevel)`; the brief is
  `$root/CLAUDE.local.md`.
- If the checkout is the repo's main checkout on its default branch,
  say that the brief would reach every session there, and suggest a
  worktree (`noemeo-worktree`). Go on if the developer wants it here.
- If `CLAUDE.local.md` already exists, read it and ask whether to
  replace it, update it, or keep it. Keep any part the developer wrote
  that isn't a brief section, under `## Notes`.

## 2. Pick the source

- A spec: list `docs/operational-specs/*.md` and ask which one, unless
  the developer named it. Read it whole. If it isn't approved (its
  status says so), tell the developer and ask before going on.
- No spec: the developer's request, in their words. Ask for what's
  missing: what the task delivers, and how they'll know it's done.

## 3. Write it

**With a spec**, the brief is these sections, in order. Text marked
*verbatim* is copied from the spec character for character.

```markdown
# Brief: <the task in one line>

Spec: <spec title> @ <commit>

## Requirements

### <requirement heading, verbatim>

Accepted when: <verbatim>
Verified by: <verbatim>

## Definitions

<the Scope's definitions of terms the requirements above use, verbatim>

## Standing rules

<the spec's Standing rules, verbatim>

## Carried elsewhere

- <heading of each requirement carried by another change or the owner, verbatim>

## Notes

<the developer's own notes, if any>
```

- `<commit>` is the spec's approved version:
  `git log -1 --format=%h -- <spec path>`. If that prints nothing (the
  spec isn't committed) or `git status --porcelain -- <spec path>`
  prints anything (it has local edits), the approved version isn't the
  file you read: tell the developer, and write `@ uncommitted` only if
  they want to go on.
- Requirements: those the spec marks "Carried by: the change", in the
  spec's order. Each gets exactly the heading and the two lines above.
- A section with nothing to hold is left out.

**Without a spec:**

```markdown
# Brief: <the task in one line>

## Task

<what the change delivers, in the developer's words>

## Accepted when

- <each criterion the developer gave>

## Out of scope

- <what the developer said this change doesn't do>

## Notes
```

## 4. Keep it out of Git

```bash
cd "$root"
git ls-files --error-unmatch CLAUDE.local.md 2>/dev/null && echo TRACKED
git check-ignore -q CLAUDE.local.md \
  || printf 'CLAUDE.local.md\n' >> "$(git rev-parse --git-path info/exclude)"
```

- `--git-path` finds the exclude file from a linked worktree too, where
  `.git` is a file; the entry then covers every worktree of this clone.
- `TRACKED` means it was committed earlier: tell the developer, and
  remove it from the index (`git rm --cached CLAUDE.local.md`) only if
  they agree.

## 5. Hand it over

Show the developer the brief and ask them to correct it. Then say:
- this session has it now; a new session loads it at launch;
- another session already running sees it only after its next
  compaction, so start a fresh one there for a big change;
- before the PR, its final text goes in the PR description.

## Updating it

Edit the file in place, show the developer what changed, and keep the
section shapes above. With a spec, a changed requirement comes from a
new spec version: re-copy from it and update the `Spec:` line.
