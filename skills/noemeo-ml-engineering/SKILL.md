---
name: noemeo-ml-engineering
description: Designs or reviews classical machine learning work in Noemeo repos -- framing, baselines, data splits and leakage, metrics, training reproducibility, model evaluation and fairness checks, packaging and serving (including GPU batch jobs), and drift monitoring -- with measured results. Use when building or changing a trained (non-LLM) model, clustering/similarity or scoring model, embedding pipeline, or self-hosted model inference, or when asked to review ML code, experiments or evaluation.
---

# Noemeo ML engineering

Procedure for the AI engineering role (`roles/engineering/ai-engineering.md`)
for trained models and self-hosted inference. LLM API work:
`noemeo-llm-engineering`.

## Step 1: Frame it

State the decision the model supports, the input, the prediction, and
how success is measured in product terms. Check the decision log
(`../noemeo-foundation/decisions/`, especially 0003: a self-hosted or trained model
needs a forcing case) and the repo's `CLAUDE.md`/`docs/decisions/` for
data-custody rules -- user content may not be usable for training at
all without consent.

## Step 2: Baseline first

Start with the simplest thing: a rule, a heuristic, a pretrained model
used as-is, or a linear/tree model. Record its metrics. Anything more
complex has to beat it by a margin worth its cost.

## Step 3: Data

- Splits that match how the model is used (by user, by time, by group)
  so near-duplicates or the same subject don't land on both sides.
- Leakage check: no feature that wouldn't exist at prediction time.
- Label quality: sample and inspect; report noise if found.
- Record data version/hash with every experiment.

## Step 4: Train and evaluate reproducibly

- Fixed seeds, pinned dependencies, logged hyperparameters and data
  version; results reproducible from the logged config.
- Metrics chosen for the decision (precision at the operating point,
  calibration, ranking metrics), reported with variance or confidence
  intervals, on a held-out set not used for tuning.
- Error analysis on slices; fairness checks per relevant group where the
  model affects people.

## Step 5: Package and serve

- Inference code is a pure function behind a driver (decision 0002);
  model artifacts versioned and loaded explicitly.
- Heavy dependencies (GPU/ML frameworks) stay out of lightweight
  packages that don't need them; GPU work runs as batch jobs with
  scratch data deleted after the run.
- Measure latency, memory and cost per prediction on the target
  hardware; quantization/distillation only with before/after numbers.

## Step 6: Monitor

Define what drift looks like (input distribution, prediction
distribution, outcome metric), how it's measured, and the threshold for
retraining or rollback.

## Step 7: Report

Framing, baseline vs. model metrics on the same held-out data, data and
split description, reproducibility details, serving cost/latency, and
open risks. For a review: findings (Severity, Where, Finding, Fix)
against steps 1-6.
