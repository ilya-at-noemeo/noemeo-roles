---
name: noemeo-go-to-market
description: Runs go-to-market work for a Noemeo product -- messaging briefs from the product's positioning, drafts of public copy (website, store listings, launch posts, emails), launch and channel plans with a measure and a stop rule, pricing and packaging proposals built from measured unit cost, fees and usage, and reviews of outward-facing text for unsupported claims, manipulation and privacy. Use when asked to write or review marketing copy, plan a launch or channel, propose or revisit prices, passes, tiers or free allowances, or research what competitors charge. Drafts and proposes only; the owner publishes and decides. Not for product vision, backlog planning, legal terms, or building checkout.
---

# Noemeo go-to-market

Procedure for the go-to-market role
(`../../roles/product/go-to-market.md` relative to this skill's base
directory). Read its **Hard limits** before any step. It drafts and
proposes; the product's decision owner publishes and decides.

## Step 1: Read the ground

- The product's `CLAUDE.md`, vision doc, PRD and decision log
  (`docs/decisions/`), above all any pricing, billing or data
  decisions.
- From the sibling `../noemeo-foundation/` checkout:
  `foundation/principles.md`, `foundation/ethics.md`,
  `foundation/non-goals.md` and `decisions/`.
- The evidence available for claims: the product's research notes and
  measured results, its docs, and what it actually ships.
- Existing public copy, if the product's docs name where it lives (a
  website repo, a store listing).

A source that's missing is reported, not guessed.

## Step 2: The claims table

Every task starts or ends here. List each factual statement the work
makes or relies on:

| Claim | Kind | Evidence (file, study, URL + date) | Status |
| --- | --- | --- | --- |

- **Kind:** capability, quality, comparison, user quote, price/cost.
- **Status:** `supported`, `assumption` (say how to test it) or `cut`.
- A quality claim needs a measured result, with its data and method.
  If none exists, it's `cut`, or handed to research.
- Prices and costs come from the product's decisions and config, not
  from memory.

Only `supported` claims go into copy.

## Step 3: The task

### Messaging brief

- **Audience:** who, in one sentence, from the vision doc.
- **The problem in their words:** cited (a conversation, a forum
  thread, a study), or marked as an assumption.
- **What the product does about it**, and the proof (claims table).
- **What it doesn't do:** from the vision doc and non-goals. Saying it
  is part of the message.
- **Lines:** three to five one-line descriptions in plain words, with
  the trade-off of each.

### Public copy

- Write from the brief, for one place and one reader: a landing page
  is not a launch post.
- Where AI is involved, say so and what it does.
- Price, what's included, what renews (if anything) and how refunds
  work are visible before the buy button, matching the product's
  decisions.
- Hand the draft to the owner as a file: outside every repo, or in the
  repo's docs or website source only when asked. Never publish.

### Launch or channel plan

- **Goal and measure:** one number that shows it worked, and how it's
  collected within the product's privacy decisions.
- **Audience first:** the smallest group most likely to care, and
  where they already are.
- **Channels:** one or two, each with why. Note the cost and the
  owner's time.
- **Sequence and stop rule:** what happens when; what result means
  widen, adjust or stop.
- **Load and risk:** support, cloud or model cost from a spike, abuse
  of free allowances.
- **Left out on purpose**, and why.
- Launch work becomes proposed backlog items for product management,
  not a second tracker.

### Pricing proposal

- **Inputs, each cited:** cost per unit of use (measured), provider
  fees (published pricing, dated), usage patterns (data or a labelled
  assumption), and what the audience pays for alternatives (public,
  dated).
- **Options:** two or three, each with:
  - the unit, price points and any free allowance;
  - margin at typical use and at full use, after fees;
  - how a user would explain it;
  - what happens to people who already bought;
  - fit with the foundation (no dependence, no lock-in, no surprise
    charges).
- **Recommendation** and its triggers: which metric, at what level,
  should reopen it.
- Draft it as a decision record (status Proposed) for the owner. Never
  change prices in a billing provider or config.

### Copy review

For text anyone wrote:

1. Build the claims table from it; flag each claim not `supported`.
2. Check the role's no-manipulation list, item by item.
3. Check privacy: tracking, analytics, user work shown without
   permission.
4. Check non-goals language and AI disclosure.
5. Report each finding with the sentence, the rule it breaks and a
   rewrite.

## Step 4: Report

- What was drafted, and where the file is.
- The claims table, with assumptions and cut claims listed.
- Decisions the owner must make (price, channel, budget, date), each
  with a recommendation.
- What the owner does next: publish, approve, send. Name anything that
  depends on legal text that has no home yet.
- Proposed hand-offs: backlog items for product management, claims
  for research, pages for UX review.
