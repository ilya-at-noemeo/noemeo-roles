---
name: noemeo-llm-engineering
description: Designs or reviews an LLM-backed component in a Noemeo repo -- whether a model belongs there at all, provider and model choice, structured output, the client seam and driver/agent boundary, retrieval, tool use and agent loops, timeouts, cost and latency measurement, and evaluation -- using noemeo-agent-kit's plumbing and Noemeo's decisions. Use when adding or changing an LLM call, agent, RAG pipeline or model/provider, when choosing between an LLM and deterministic code, or when asked to review LLM integration code or design.
---

# Noemeo LLM engineering

Procedure for the AI engineering role (`roles/engineering/ai-engineering.md`)
on anything that calls an LLM. Prompt text itself: use
`noemeo-prompt-engineering`. Classical models: `noemeo-ml-engineering`.

## Step 1: Context

Read the generic decision log (`../noemeo-foundation/decisions/` from
the current repo's root, a sibling checkout), especially 0002 (driver/agent boundary) and 0003
(build capacity, not usage), and the current repo's `CLAUDE.md` and
`docs/decisions/` (products record their own rules there: where LLM
calls may go, what may be sent, which transport applies in which
mode). Look at how existing agents in the repo are built before adding
a new pattern.

## Step 2: Does this need an LLM?

Write down, for the component: the input, the output, and what "right"
means. If the rule can be stated precisely (thresholds, lookups,
parsing, routing on known fields), it's deterministic code -- say so
and stop. Use an LLM only for real judgment or language understanding,
and keep the deterministic parts (validation, scoring rules,
pass/fail decisions) outside the model.

## Step 3: Design the call

- **Boundary (0002):** the agent module takes plain parameters and
  returns a typed (Pydantic) result; the driver reads config/env and
  picks the client. No environment reads or transport branching inside
  the agent.
- **Client seam:** use `noemeo-agent-kit` -- `llm_openai` or
  `llm_cloud` `build_structured_llm`, called through
  `structured_output.invoke_structured`, which returns parsed output
  plus `TokenUsage`. A new provider is a new sibling module with the
  same return contract, added only with a real reason (0003).
- **Model choice:** check current model IDs, context limits, pricing
  and structured-output support in the provider's docs now -- not from
  memory. Prefer the smallest model that passes the eval (step 5). Keep
  the model a parameter, not a constant buried in the agent.
- **Structured output:** every field has a purpose and a type; enums
  over free strings; required fields only (strict-mode schemas reject
  defaults/optional fields). Treat output as untrusted: validate, and
  never let the model supply identity, ownership or permissions.
- **Robustness:** an explicit timeout (agent-kit's default), bounded
  retries, and a defined behaviour on refusal, guardrail block,
  malformed output and timeout -- surfaced to the user, not swallowed.
- **Context:** send only what the call needs (recent turns plus a
  summary, not the whole history); images at the lowest detail that
  works. Product rules on what may leave the machine win.
- **Retrieval / agents (only if needed):** retrieval before
  fine-tuning; the same embedding model at index and query time; tool
  calls with typed arguments and a step limit; no tool that acts on
  identity or money without a deterministic check.

## Step 4: Cost and latency

Estimate tokens per call and calls per user action, multiply by current
prices, and state the per-action and monthly figure. After building,
replace estimates with measured `TokenUsage` and P50/P95 latency from
real runs.

## Step 5: Evaluation

Before calling it done: a small golden set (inputs plus expected
outputs or rubric), run before and after any prompt/model change. For
LLM-as-judge, check agreement with human labels first. Mocked unit
tests cover parsing and control flow; live evals cover quality -- keep
paid live checks as scripts outside the test suite and say when they
were last run.

## Step 6: Report

For a design: the component table (input, output, model or
deterministic, why), the client/driver wiring, model and cost
estimate, failure behaviours, and the eval plan. For a review: findings
table (Severity, Where, Finding, Fix) against the steps above, plus
what was measured vs. assumed.
