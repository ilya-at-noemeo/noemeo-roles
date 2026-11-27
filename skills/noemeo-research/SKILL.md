---
name: noemeo-research
description: Runs research in Noemeo repos -- framing a falsifiable question, checking prior work and whether it covers today's models, choosing and licensing public benchmarks, designing controlled experiments with repeated runs and validated graders, running them within a budget, keeping raw data immutable, and writing research notes and publication packages (including null results). Covers both model-on-dataset evaluations and agent-methodology experiments (isolated agent sessions as arms, blind-scoring their artifacts, inter-rater reliability), with studies kept in the dedicated noemeo-research repo. Use when asked to study, measure or evaluate how a model-backed feature or an agent behaves, compare conditions, build an evaluation on a public dataset, or prepare results for publication.
---

# Noemeo research

Procedure for the research role (`roles/research/research.md`). Engineering
procedures it leans on: `noemeo-llm-engineering` (evals, LLM-as-judge),
`noemeo-prompt-engineering` (prompt hashes, before/after on the same
inputs), `noemeo-ml-engineering` (splits, leakage).

## Step 1: Read the ground rules

The product's `CLAUDE.md`, its research index (where studies live, their
layout, data rules) and `docs/decisions/`, plus the generic decision
log in `../noemeo-foundation/decisions/` (a sibling checkout). Note
what may not be used (users' content, sessions,
paid calls without approval) before designing anything.

**Where the study lives.** Noemeo's research home is the dedicated
`noemeo-research` repo (a sibling checkout), not the product/infra repos --
keeping study data, transcripts and bespoke scripts out of deployables. Put
methodology/agent studies under `methodology/<YYYY-MM-slug>/` and product-AI
studies under `photo/<YYYY-MM-slug>/`; read that repo's `CLAUDE.md` for the
conventions. A study that audits product code **pins its commits/tags by
reference** and never copies that code into the research repo.

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

## Agent-methodology experiments (the subject is an agent, not a dataset)

Some studies measure not how a *model* behaves on dataset items, but how an
*agent* behaves on a task -- e.g. "does a task brief change what an agent
delivers". The backbone above is unchanged (falsifiable claim, one-thing-differs
arms, controls, repeated runs, immutable data, blind graders, `metrics.json`,
null results). These additional patterns apply; follow them rather than copying
any one study's scripts verbatim (the harness is young -- patterns, not a
template):

- **Arms are headless agent sessions.** Each arm is a whole agent run launched
  as a fresh **headless CLI process** -- Claude Code (`claude -p "<task>"
  --output-format json`, optionally `--model`/`--effort`/`--permission-mode`) or
  Codex (`codex exec`, its non-interactive mode) -- **not** an in-session Task
  subagent (a subagent inherits this session's context and brief, which would
  break blinding). Both are run through `Bash`; both are **paid calls** (see the
  cost rule) and need the provider's auth configured. The harness itself can be
  the thing under test: to ask "does X help in Claude Code vs Codex", the harness
  is the arm and everything else is held constant.
- **Isolate every arm.** One **own git worktree + fresh session** per arm so runs
  can't contaminate each other (a shared working tree silently corrupts the
  comparison); use the `noemeo-worktree` skill, never a bare `git worktree add`.
  Record the harness, model, effort and session settings, held constant except
  for the one thing that differs. Capture each run's session id / transcript and
  its usage from the CLI's JSON output as immutable raw data.
- **Pin the code-under-test by reference.** Start every arm from one base commit;
  tag each arm's produced commit durably in the *product* repo; the research
  repo records the tags, never the code.
- **Score the artifacts, blind to arm.** The output is an artifact (a PR, a
  diff), not a dataset label. Anonymise and shuffle the arms' artifacts, score
  them in a fresh session with **no access to this study's brief/hypotheses**,
  against a frozen rubric. Report residual issues and coverage.
- **Inter-rater reliability across grader agents.** Two or more independent blind
  graders; report unanimous/majority rates and an agreement statistic (Cohen's
  kappa for two raters, Fleiss' for three or more). A single grader's verdict is
  a draft.
- **Cost in tokens, not only dollars.** On a subscription plan `total_cost_usd`
  from `claude -p --output-format json` is an unbilled API-price *estimate* --
  report it as such, and report output-token use (the cost/effort axis) and the
  spread. Rate-limit throttling adds latency, not tokens.
- **Rubric is itself auditable.** A hand-authored rubric is a source of error;
  version it, and when a row is wrong, correct it in a new version and re-tally
  deterministically, preserving the original.

Worked reference: `noemeo-research/methodology/2026-11-briefs-gap-analysis/`
(arms, blind grading, inter-rater, provenance-by-reference, a corrected rubric).
Reusable helpers graduate into `noemeo-research/lib/` only on second use.

## Report

Start with the claim and the verdict (supported / not supported /
inconclusive) in one line. Then the numbers with their spread, the
controls, what wasn't measured and why, cost spent, and the recommended
next step. Never present a draft label, an unvalidated grader or an
estimate as a result.
