---
name: noemeo-ship
description: Takes a change in a Noemeo repo from request to open pull request -- plan, branch, implement, tests by noemeo-test-engineer, review by noemeo-code-reviewer until it's Ready, then commit, push and PR -- one step at a time, without skipping the test or review step. Use when asked to ship, finish, land or "take to PR" a change, fix or feature end to end, or when a change is implemented and only tests, review and the PR remain. Not for research studies (noemeo-research) or design-only work (noemeo-backend-architect).
---

# Ship a change

The main session runs this chain itself. It plans and implements, then
hands testing and review to their roles' agents in fresh contexts.
Each step has an exit condition; don't move on until it's met. Tell
the user in one line when each step starts.

## 1. Plan

- Read the repo's `CLAUDE.md`, its decision log (`docs/decisions/`) and
  the foundation's (`../noemeo-foundation/decisions/`, if checked out).
- Restate the change: what changes, what doesn't, which repos, and how
  you'll know it works.
- A non-trivial design (new boundaries, data custody, a new service or
  provider) goes through `noemeo-design-review` first. A design that
  still needs deciding goes to `noemeo-backend-architect`, not into code.
- Ask the user only what's undecided and theirs to decide: scope, data
  use, paid calls and their budget. A choice with a conventional
  default is made and stated.

**Exit:** a short plan the user has seen, with its open decisions settled.

## 2. Branch

- Never commit to a default branch. Branch from the PR's base, fetched
  fresh: the repo's default (`origin/HEAD`), or `dev` where the repo
  promotes `dev` to `prod`.
- Several repos get one branch each, with the same name.
- Note anything already uncommitted in the tree, and leave work that
  isn't yours alone.

**Exit:** on a fresh branch from the right base.

## 3. Implement

- Write code that reads like the code around it.
- Keep to the repo's boundaries (drivers read configuration, agents
  receive plain parameters) and its rules on secrets, data and paid calls.
- Paid model or cloud calls need the user's approval and budget. Run
  a first small batch, report its measured cost, then continue.
- AWS only through the project's named profile from `~/.aws/config`,
  never the default credentials.
- Run the repo's own checks (lint, format, tests) until they pass.

**Exit:** the change works and the repo's checks pass.

## 4. Tests: noemeo-test-engineer

Spawn `noemeo-test-engineer` for every behaviour the change adds or
alters that no existing test would catch. Give it:
- the repo's absolute path and branch;
- the behaviours to cover;
- what may not be touched (real data, paid calls, secrets).

It writes tests only, proves each can fail, and wires them into the
repo's checks.

Skip it only for a change with no behaviour to test (documentation,
configuration text), and say so in the PR.

**Exit:** the new tests pass and the agent has shown they fail without
the change.

## 5. Review: noemeo-code-reviewer

- Spawn `noemeo-code-reviewer` on the branch against its PR base, naming
  each repo by absolute path. Give it:
  - what the change is for and the risky parts to probe;
  - what it may not do (paid calls, AWS calls, secrets).
- Fix every defect and any nit worth fixing. Then send the fixes back
  to the same reviewer (SendMessage) for a re-review of the delta.
  Repeat until every repo is **Ready** or **Ready with nits**.
- The PR gate compares the reviewed fingerprint with the tree as it is.
  Any edit after the last verdict, formatting included, needs one more
  confirming round.
- Run a formatter only on files you changed, with the repo's own
  configuration. Another repo's settings rewrap files you never meant
  to touch.

**Exit:** a Ready or Ready-with-nits verdict on the final state of
every branch.

## 6. Pull request

- Commit in logical pieces, ending each message with the attribution
  lines the session gives, and keep the repo's commit identity.
- Write the PR body with the file tool, **outside the repo** (the
  session's scratchpad or a temp directory), and pass it with
  `--body-file <path>`. A file inside the repo is untracked work: it
  changes the reviewed fingerprint, and the gate denies the PR. Don't
  put the body in an inline quoted `--body "..."` either: the guard
  reads backticks and `$(` there as commands. It only skips a heredoc
  that feeds `git commit` or `gh pr`; a heredoc feeding anything else,
  `cat > file` included, is scanned.
- The body covers:
  - what changed and why;
  - the evidence (measured numbers, test counts);
  - the review rounds, and what was fixed or accepted;
  - anything the change needs to go live (deploy order, a plugin
    update, another repo's PR first);
  - a test plan, with what's left unchecked marked as such.
- Push and open the PR in one command that **starts with
  `cd <repo> &&`**. The gate recognises only that leading form; with
  anything else (`cd X;`, a variable assignment first, a later `cd`),
  it checks the session's working directory instead.
- Several repos: open the PR others depend on first, and say the order
  in each body.

**Exit:** PR links in hand. Report them with what's left for the user:
merging, deploying, and decisions the change surfaced. Never merge or
deploy unless asked.
