---
name: noemeo-research
description: Runs research in Noemeo repos -- framing a falsifiable question, checking prior work and whether it covers today's models, choosing and licensing public benchmarks, designing controlled experiments with repeated runs and validated graders, running them within a budget, keeping raw data immutable, and writing research notes and publication packages (including null results). Use when asked to study, measure or evaluate how a model-backed feature behaves, compare conditions, build an evaluation on a public dataset, or prepare results for publication.
---

# Noemeo research

Procedure for the research role (`research/research.md`). Engineering
procedures it leans on: `noemeo-llm-engineering` (evals, LLM-as-judge),
`noemeo-prompt-engineering` (prompt hashes, before/after on the same
inputs), `noemeo-ml-engineering` (splits, leakage).

## Step 1: Read the ground rules

The product's `CLAUDE.md`, its research index (where studies live, their
layout, data rules) and `docs/decisions/`, plus the generic decision
log in `../noemeo-foundation/decisions/` (a sibling checkout). Note
what may not be used (users' content, sessions,
paid calls without approval) before designing anything.

## Step 2: Frame the claim

Write, before collecting data:

- **Question** and **claim**, falsifiable: what result would show it
  wrong.
- **Conditions**: what differs between them -- one thing.
- **Measures**: primary and secondary, how each is computed, and which
  is decisive.
- **Controls**: cases that must not change (real errors still caught,
  strong items left alone), and how run-to-run variance will be seen.
- **Decision**: what result leads to shipping, dropping or a follow-up.

Put it in the study's `README.md` first; changes after seeing data are
recorded as such.

## Step 3: Prior work

Search for published results (WebSearch; papers, benchmarks, datasets).
For each relevant one, record task, models, data and numbers, and judge
whether it covers our case:

- Same task and comparable data, and models of the current generation
  -> cite it and don't re-measure.
- Older model generations, different task or data -> not evidence about
  today's system; the claim needs measuring.

Say what you searched and what you didn't find; absence of a result in a
quick search isn't proof none exists.

## Step 4: Data

- **Public benchmarks for publishable claims.** Choose datasets whose
  labels give the ground truth the claim needs (e.g. a label that makes a
  quality deliberate by construction). Product-owned data is a secondary
  set for what no public set has.
- **Terms.** Read each dataset's licence and terms of use; record them in
  the study. Non-commercial or "research only" data is for evaluation and
  publication, never for calibrating a product. Unclear terms are flagged
  for a qualified person, not settled here.
- **Fetching.** Fixed seed, a committed list of item ids and labels, the
  items themselves git-ignored. Respect the source's crawl rules; make
  downloads resumable; size downloads to the space actually available.
- **Never redistribute** others' images or text; publish ids, labels and
  our own measurements.

## Step 5: Design and budget

- One change per comparison; same inputs, seeds and model settings
  across conditions; prompt hashes recorded with every output.
- **Repeated runs**: three or more per item and condition when outputs
  vary; report the spread, and the flip rate of the controls.
- **Blind human judgement** for preferences: items in random order,
  conditions hidden.
- **Graders**: a rule when one suffices; an LLM grader only with a fixed
  question per case, validated on a blind human-labelled subset with the
  agreement reported.
- **Cost**: estimate, run a small first batch, report its measured cost,
  and get the owner's approval before scaling up. No paid calls without
  an approved budget.

## Step 6: Run and keep the record

- `data/`: raw outputs and labels as written, never edited; corrections
  are new rows or files with a note.
- `scripts/`: what produced each output, and `analyze.py` writing
  `metrics.json`. Every number in the write-up comes from it; no hand
  counts.
- Log failures (API errors, missing items) rather than silently dropping
  them.

## Step 7: Write up

Every study gets a research note in its `README.md`: status, question,
setup, data and terms, measures, results (from `metrics.json`, with
spread or intervals), threats to validity, what a publication would still
need, how to reproduce. Null and negative results are written up the same
way and added to the research index.

## Step 8: Publication package (when a result holds)

Only after the result survives repeated runs and controls:

1. **Venue and form**: workshop, conference, journal or preprint, with
   its format and policies (including on AI-assisted writing).
2. **Related work**: from step 3, positioned honestly.
3. **Method and results**: enough to reproduce; uncertainty reported;
   ablations for each component of the change.
4. **Reproducibility package**: code, item ids, labels, prompts and
   model versions; no third-party images.
5. **Rights and ethics**: dataset licences, consent for any identifiable
   people, the owner's own content only with their decision.
6. **Authorship and disclosure**: who did what, and how AI assistance was
   used.
7. **Owner approval** before anything is submitted or posted. Research
   prepares; the owner submits.

## Report

Start with the claim and the verdict (supported / not supported /
inconclusive) in one line. Then the numbers with their spread, the
controls, what wasn't measured and why, cost spent, and the recommended
next step. Never present a draft label, an unvalidated grader or an
estimate as a result.
