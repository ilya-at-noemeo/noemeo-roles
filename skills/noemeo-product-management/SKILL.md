---
name: noemeo-product-management
description: Runs product management for a Noemeo product -- collecting loose commitments (deferred follow-ups, temporary decisions, open risks, unchecked test plans) across its repos into the open-items backlog, planning milestones with exit criteria and blockers, writing feature requirements with acceptance criteria, proposing priorities for the owner to rank, and reporting status. Use when asked what's open or forgotten across a product's repos, what's next on a product's roadmap, what blocks a release, to plan a milestone, write up a feature's requirements, or triage the product backlog. Not for product vision or positioning, design, code-level tech debt, or marketing.
---

# Noemeo product management

Procedure for the product management role
(`../../product/product-management.md` relative to this skill's base
directory). It proposes; the product's decision owner decides.

## Step 1: Read the ground

- The product's `CLAUDE.md`, vision doc, PRD or requirements doc, and
  decision log (`docs/decisions/`), plus, from the sibling
  `../noemeo-foundation/` checkout, `decisions/`,
  `foundation/principles.md`, `foundation/non-goals.md` and the
  README's "Open Items" convention.
- **The backlog**: open items are GitHub issues in noemeo-foundation
  (private, so they may name products), labelled `role:<name>`. Read
  them all, not only this role's:
  `gh issue list --repo <owner>/noemeo-foundation --state all --limit 200 --json number,title,state,labels,milestone,body`
  and its milestones,
  `gh api 'repos/<owner>/noemeo-foundation/milestones?state=all'`.
  Take `<owner>` from `gh repo view --json owner -q .owner.login` in
  that checkout.
- The repos the product's docs name, from their sibling checkouts.

## Step 2: Backlog conventions

The foundation README's convention, extended for planning:

- **Where:** every open item goes in noemeo-foundation, one issue per
  piece of work, its title prefixed with the product, as in
  `[<product>] <outcome>`; older items keep their titles until someone
  touches them (retitling is a proposed change like any other). Never in
  a public repo: an issue there is
  publishing, and generic repos never reference products. Work in a
  generic repo is described there only through its own changes, in
  generic terms, when the change is made.
- **Title** says the outcome, not the activity ("Release notes list
  every breaking change", not "Look into release notes").
- **Body**, in this order:
  - **Why** -- the vision, decision, study or conversation it serves.
  - **Done when** -- checkable criteria.
  - **Source** -- where the commitment came from (repo, file and line;
    PR and section), so it can be traced and closed with it.
  - **Depends on** / **blocks** -- other issues.
  - **Needs a decision** -- the question, if the owner must answer
    before work starts.
- **Labels:** `role:<name>` for the role that acts next (the README's
  list plus `role:product-management`), and, created on first use,
  `follow-up` (deferred from a merged change), `risk` (could hurt users,
  money or a release) and `needs-decision`. The body is authoritative for
  dependencies and the open question; labels are only for filtering.
- **Milestones** for a product's releases, named
  `<product>: <release>`. The description holds the exit criteria and
  the owner's ranking as an ordered list of issue numbers -- the one
  place the order is kept and read back. A due date only when the owner
  sets one.
- Resolved items close; a durable decision that came out of one goes in
  the right decision log, referencing the issue (the README's rule).

## Step 3: The task

Do the one asked for.

### Sweep: collect loose commitments

Search, in each of the product's repos:

- decision records whose status is temporary or has an exit condition;
- "open questions", "risks", "follow-ups", "not yet", "deferred" and
  numbered open items (`Q1`, `R-2`) in product docs;
- merged pull requests: follow-up and nit sections and unchecked `- [ ]`
  test-plan items in the body, and deferred points in review comments
  (`gh pr list --state merged --limit 50 --json number,title,body,comments,reviews`,
  run from each repo's checkout);
- `TODO`/`FIXME` in code only when it names work, not style.

For each, check it isn't already done (read the current code or doc)
or already an issue. Output a table -- proposed title, source, why it
matters, done-when, suggested labels -- with duplicates merged and
finished items listed separately as "already done".

### Milestone plan or release readiness

State the milestone's purpose in one sentence and its exit criteria.
List what blocks it (each with its issue), what's in, what's
deliberately out and why, and the dependency order. Mark every
criterion that's an assumption rather than a verified fact.

### Feature requirements

First check the feature against the Noemeo Test and the non-goals; if
it fails either, or doesn't fit the product's vision, say so and hand
it to product vision instead of writing requirements. Otherwise: problem
and who has it; evidence (cited) or "assumption to test"; the success
measure; non-goals; acceptance criteria; questions for architecture, UX
design and research, each addressed to its role.

### Prioritize

For each candidate: impact (on whom, how much), effort (rough, from
the code), risk if left, confidence in the estimates, and what it
unblocks. Propose an order with a sentence of reasoning per item, and
the single item to do next. The owner ranks; the ranking then goes in
the milestone's description.

### Status

Since a date or milestone: done (with the change that did it), in
progress, blocked (on what), and stale (no movement, or source changed
since the issue was written).

## Step 4: Tracker changes are proposals

Write nothing to the tracker yourself. Return every change you propose
-- issues to create or edit, labels, milestones, the ranking -- as exact
`gh` commands (bodies in files outside any repo, passed with
`--body-file`), for the main session to run once the owner has seen and
approved them. Never propose closing, deleting or transferring an issue
without saying why each one should go. Never post, publish or send
anything anywhere.

## Step 5: Report

1. **Answer** -- the plan, list or verdict in a few sentences.
2. **The table or plan** from Step 3.
3. **Decisions needed** -- each question for the owner, with the
   options and a recommendation.
4. **Proposed tracker changes** -- the `gh` commands from Step 4, or
   "none".
5. **Not checked** -- sources not read, repos not available.
