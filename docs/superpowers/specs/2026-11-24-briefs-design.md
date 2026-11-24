# Briefs: design

- **Status:** draft for the owner's approval, 2026-11-24. Replaces the
  hook-delivered draft of the same day (pinned commits, pointer, guard),
  which the owner found too heavy.
- **Builds on:** the spec analysis design (2026-11-21), which defines
  what a brief contains when a task has a spec.
- **(owner)** marks what the owner decided; the rest is proposed.

## Goal (owner)

Make the developer's life easier, not impose restrictions. Governance as
native to the agent tool as possible, with minimal overhead.

## Why (owner)

The scalability of AI-assisted software engineering is constrained not
only by the agent's coding capabilities, but also by its ability to
identify, retain and apply organizational knowledge.

An agent may produce excellent code in isolation while failing to
comply with applicable policies, architectural decisions, requirements
and acceptance criteria. As the system and its body of organizational
knowledge grow, discovering all relevant constraints becomes
increasingly difficult. Long-running sessions further dilute the
information that governs implementation.

Briefs address this problem by separating knowledge selection from task
execution.

The specification analysis process identifies and reconciles the
critical information applicable to a task. The approved brief delivers
that information to the agents doing the work in a compact,
authoritative and persistent form, regardless of session lifecycle or
context compaction.

This allows organizational knowledge to scale without requiring every
agent doing the work to process the entire knowledge base.

The intended outcomes are below. They are hypotheses, not results:
each is measured against a baseline of the same kind of work without
briefs before it is claimed.

- Improved compliance with applicable requirements and policies.
- Higher first-pass reviewer acceptance rates.
- Fewer implementation and review iterations.
- Lower total cost per accepted task.
- Reduced dependence on human intervention.

The brief guarantees controlled delivery of approved information, not
compliance itself. Independent review verifies the resulting
implementation against the authoritative specification.

Approved task requirements live longer than a conversation: a task
spans sessions, compactions and agents, while the conversation is
compacted and belongs to one session. The brief carries the task's
requirements across that gap.

## What a brief is

| Part | Job |
| --- | --- |
| `CLAUDE.md` (permanent) | How agents must work in this repo or directory |
| The spec | What must be achieved, approved, versioned |
| The brief, `CLAUDE.local.md` (owner) | This task's requirements and acceptance criteria, for the agents doing it |
| Skills | Create the brief, and fold lasting knowledge back into `CLAUDE.md` |

The brief is the `CLAUDE.local.md` at the worktree's root: ignored by
Git, so it exists only in that worktree, for that task. With a spec, its
content is the spec analysis brief (requirement headings, "Accepted
when", definitions, standing rules). Without one, it is the task as the
developer states it. It never copies `CLAUDE.md`.

It is the developer's file (owner): the developer reviews and corrects
it, and the session may update it when the task's understanding
changes.

## How

1. **Create.** A dedicated skill writes `CLAUDE.local.md` (owner): from
   the spec with the spec analysis brief command when there is a spec,
   otherwise from the request. The developer reviews and edits it.
2. **Offer.** The ship skill, when the worktree root has no
   `CLAUDE.local.md`, offers the developer to create one (owner). Never
   required.
3. **Work.** Claude Code loads `CLAUDE.local.md` at launch, re-reads it
   after compaction, and custom subagents load it too; Explore and Plan
   don't, and the parent agent has it. A brief created inside a session
   is in that conversation already; a fresh session picks it up from
   the file.
4. **Before the PR** (ship skill):
   - **Fold back (owner).** Lasting working knowledge the task produced
     (a new hazard, convention or boundary) goes into the relevant
     permanent `CLAUDE.md`, reviewed in the PR like any change. Task
     requirements don't: they stay in the spec, and a `CLAUDE.md` gets
     at most one line pointing to it.
   - **Record it in the PR description (owner).** The brief's final
     text goes into the PR description, folded, so the reviewer sees
     what the agent worked against and the record survives the
     worktree. It is never committed to the repo (owner): the creating
     skill adds `CLAUDE.local.md` to the repo's `.git/info/exclude`,
     which ignores it in every worktree without changing a tracked
     file.
5. **End.** The worktree is removed after merge, and the brief with it.

## Briefs and `CLAUDE.md`

| | `CLAUDE.md` | Brief (`CLAUDE.local.md`) |
| --- | --- | --- |
| Says | How to work here | What this task must deliver |
| Applies to | Every session in the directory | Sessions in the task's worktree |
| Lifetime | Permanent | The task |
| In Git | Yes | Never; its final text is in the PR description |
| Changed by | A reviewed PR | The developer and the session |

The task's requirements can't go in `CLAUDE.md`: they would reach every
session, and after merge every future one. In a dry run on a real
spec (26 requirements, about 25,000 characters, touching three repos),
some weren't about code at all (third-party setup, legal documents,
agreements) and others had no single directory to sit in.

## Limits

- **Not enforcement.** The brief helps the agent know the requirements;
  the reviewer checks the code against the spec.
- **Soft by design.** A missing or edited brief isn't blocked. The
  developer sees it in the session, and the reviewer sees the final
  text in the PR.
- **A running session after a big brief change** may mix old and new
  text after its next compaction; a fresh session avoids that.
- **Claude Code only.** Codex reads its own instruction files; its
  equivalent is open.

## Verified

Measured 2026-11-24 with Claude Code 2.1.331, in a throwaway repo, by
asking the agent (no tools allowed) to quote marker lines:

- **Compaction re-reads it from disk.** The markers were changed in the
  file mid-session. Before `/compact` the session still quoted the old
  ones; after it, the new ones, which it had never seen.
- **Subagents:** general-purpose and a custom subagent quoted the
  brief's marker; Explore didn't. The subagents' own transcripts show
  the marker wasn't in their prompts.

## Rejected

- **Hook delivery from pinned commits, with a guard that blocks work
  without a valid brief.** Too much machinery for the developer, and
  that spec's brief (about 20,000 characters) is twice the hooks'
  10,000-character limit.
- **All requirements in a directory's `CLAUDE.md`.** See the dry run
  above.
