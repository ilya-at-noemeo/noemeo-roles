# Working agreement

Rules for every role, in every Noemeo repo, whichever agent tool or
person does the work. A role's own limits are stricter where they
differ: a role that may not make live calls doesn't gain that
permission here.

## Sources

- Before work, read the repo's `CLAUDE.md` (and any nested one
  governing the files you change), the docs it names for the area, its
  `docs/decisions/` if it has one, and the generic decisions in the
  sibling `noemeo-foundation/decisions/`. In a linked worktree, find
  siblings through the main checkout (`git rev-parse --git-common-dir`).
- Load the role for the work at hand, and the skill that carries it
  out. A missing source is reported, not guessed.

## Orchestration

- The main session is a **thin router**, not the worker. When a request is
  a self-contained specialist task -- research, review, architecture,
  tests, a bounded implementation -- hand it to that role as a subagent and
  keep only its conclusion; don't do the work inline in the main thread.
- Why it is cheaper and sharper: a single long session re-reads its whole
  history every turn (cost grows with its length) and eventually compacts
  it into lossy summaries. Segmenting by topic keeps each context short --
  cheaper to re-read, better cache reuse, sharper attention, and no
  "summaries of summaries" amnesia; the specialist works the real task, not
  a distilled one.
- Granularity: delegate work whose own context would bloat the main
  thread; keep trivial or genuinely conversational turns inline -- a round
  trip for a one-line answer costs more than answering it.
- Hand off with a brief (objective, inputs, the decision to make, what to
  return -- the `noemeo-brief` discipline); isolate file work in its own
  worktree so parallel specialists don't collide. A specialist returns a
  terse, structured conclusion to the main session, which routes the next
  step; subagents return to the hub, not to each other. The owner talks to
  the main session only; it mediates every handoff and relays what matters.

## Safety

- Never read or edit secrets (the repo's `.claude/noemeo-guard.json`
  lists them beyond the usual `.env` and key files), force-push,
  recursively force-delete, or clean away untracked work.
- **AWS: Noemeo's roles only.** Any AWS call, even a read-only one,
  uses a Noemeo profile from `~/.aws/config` (one that assumes a role
  in Noemeo's account; the repo's `CLAUDE.md` names it), via
  `--profile` or `AWS_PROFILE`, in scripts and SDKs too. Never the
  default credentials: on a developer's own machine they may belong to
  a personal account. If the profile needs MFA, give the developer the
  command to run instead. Confirm the account with
  `aws sts get-caller-identity` before trusting a result.
- Paid model calls, cloud changes, deploys and anything posted outside
  the machine need the request's explicit approval, paid ones with a
  budget. That approval never overrides a role's hard limits; a role
  without them is bound by this rule alone. Run a small first batch and
  report its measured cost before continuing.
- Exception, approved by the owner: the free lookups of Semgrep (run
  with `--metrics off`), osv-scanner and trivy that
  `noemeo-security-review` lists (rule and check downloads; package
  names and versions sent to vulnerability databases) need no
  approval. Nothing else they could send -- usage metrics, source
  code, scan results, a login or upload to their services -- is
  covered, and widening that list needs the owner's approval.

## Review

- Never approve your own work. Tests are built by the testing role's
  building side; the change is checked by its checking side, in a
  fresh context without the author's reasoning.
- A review covers the files as they are: any later edit, formatting
  included, needs another review.
- Never fabricate a review record, a passed check or a measured number.
  If enforcement or independent review isn't available, say so before
  calling the work ready.

## Picking up and handing off

- Start from the actual branch, working tree, commits, issue and PR
  discussion and docs; chat history from another session or tool is
  supplementary, never the record. Preserve uncommitted work that isn't
  yours.
- Don't edit the same checkout from two sessions at once; use separate
  worktrees.
- When stopping mid-task, leave a handoff: the objective, the branch,
  changed files, the checks actually run and their results, open
  decisions and the next action.
- Durable decisions go in the existing decision log, open items in the
  existing backlog, when the owner authorises it. Never start a second
  tracker.
- Settled project knowledge (a policy, an architecture or product
  definition, a measured finding) goes to the repo's decision roots
  through the `noemeo-decisions` skill, never only into one tool's
  private memory. An agent proposes; only a person accepts.
