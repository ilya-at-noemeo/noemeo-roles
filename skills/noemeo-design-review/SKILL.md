---
name: noemeo-design-review
description: Reviews a design doc, plan, PR, diff or proposed change against Noemeo's standing decisions (the decision log in noemeo-foundation) and the current repo's own CLAUDE.md rules, and reports each violation with the decision it breaks, where, and a suggested fix. Use when asked to review a design, plan, architecture or change "against Noemeo's decisions" or for consistency, before implementing a change to cloud, infrastructure, IAM/CI, agents or a generic repo's contracts, or before committing such a change in any Noemeo repo.
---

# Noemeo design review

Checks one target against rules that are already settled. It finds
places where a design or change contradicts a decision; it doesn't
re-argue the decisions and isn't a general bug hunt (that's
`/code-review`; security is `/security-review`).

## Step 1: Pin down the target

Use what the request names: a file (design doc, plan), a PR, a branch,
or a plan in the conversation. If nothing is named, review the current
repo's uncommitted changes (`git diff HEAD`); if there are none, the
current branch against its base (`git diff <base>...HEAD`, where base is
`dev` in infra repos and `main` elsewhere). Say which target you
reviewed.

## Step 2: Load the rules

1. **Generic decisions:** read every `*.md` in the generic decision
   log, `decisions/` in the private `noemeo-foundation` repo, found as
   a sibling checkout: `../noemeo-foundation/decisions/` from the
   current repo's root (start with its `README.md` index). Use only
   decisions whose status is Accepted. If the directory can't be found,
   say so and continue with step 2.2 only -- don't invent decisions
   from memory.
2. **Repo rules:** the current repo's `docs/decisions/*.md` if it has
   a decision log (product repos do; cite these as e.g.
   `product 0001`), its `CLAUDE.md` (and any nested `CLAUDE.md` in the
   directories the target touches), plus the docs it names as
   authoritative for the area under review. In a product repo these
   hold product-specific decisions that extend the generic ones. When
   the target spans repos (e.g. a product's infra repo), also load the
   owning product's decision log if it's a sibling directory.
   Where a product rule is stricter, apply it; a product rule that
   contradicts a generic decision is itself a finding.

## Step 3: Check

Go through each decision's **Review checks** and each relevant repo
rule against the target. Verify by reading the actual code or text --
grep for the patterns, open the files -- rather than inferring from
names or from the summary in a PR description. Note a decision as clean
only after looking.

Pay particular attention to:
- anything persisted or logged by a cloud component (the product's own
  cloud-scope decision, where it has one);
- trust policies, OIDC subjects, secrets and resource ARN patterns
  (0006, 0007);
- environment/config reads and transport branching inside agents (0002);
- product names or links appearing in generic repos (0004);
- new capabilities without a named forcing case (0003).

## Step 4: Report

Start with one line: the target reviewed and which rule sources were
loaded. Then, most severe first:

| # | Severity | Rule | Where | Finding | Suggested fix |
|---|---|---|---|---|---|

- **Severity:** `Violation` (contradicts a rule), `Risk` (likely to
  lead to one, or can't be confirmed clean), `Question` (the rule
  doesn't clearly cover it; needs an owner decision).
- **Rule:** decision number (e.g. `0007`, or `product 0001`) or
  `CLAUDE.md: <section>`.
- **Where:** `path:line` as a link when possible.

Then a short **Clean against** line listing the decisions that were
checked and passed, and anything **not checked** with the reason.

Don't edit anything unless asked. If a finding suggests a decision
itself is outdated, say that explicitly and suggest recording a new
decision that supersedes it, rather than quietly accepting the
deviation.
