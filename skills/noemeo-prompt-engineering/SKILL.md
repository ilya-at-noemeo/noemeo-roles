---
name: noemeo-prompt-engineering
description: Writes, revises or reviews prompts (system prompts, instructions, few-shot examples, output schemas, agent/tool instructions, Agent Skill instructions) for Noemeo LLM components -- structure, grounding in Noemeo's principles, injection resistance, versioning with prompt hashes, and eval-driven iteration with before/after evidence. Use when creating or changing a prompt, when model output quality or format regresses, or when asked to review or harden a prompt.
---

# Noemeo prompt engineering

Procedure for the AI engineering role (`engineering/ai-engineering.md`)
for prompt text on an already-chosen model. Model/provider, schema
plumbing and agent design: `noemeo-llm-engineering`.

## Step 1: Know the job and the current behaviour

Read the existing prompt, its output schema, and where it's called.
Collect 5-10 real inputs that show the problem (or the target
behaviour) and run the current prompt on them first -- a change without
a baseline can't be shown to help. Read the repo's `CLAUDE.md` for
rules on where prompt text lives (some prompts are loaded from shared
files, not Python constants -- edit the source, don't fork it).

## Step 2: Structure

- **Role and goal** in a sentence or two; then **context** the model
  needs; then **instructions**; then **output format**. Put stable text
  first and variable input last (helps prompt caching).
- Instructions say what to do and why, not only what to avoid. One
  instruction per idea; no contradictions with the schema.
- **Examples** only when they fix a real failure; vary them so the
  model doesn't copy surface features.
- **Output:** rely on the structured-output schema for format; the
  prompt explains meaning, not JSON syntax.
- **Grounding in Noemeo's principles:** gather intent before generating
  (reveal before generate), frame outputs as suggestions the person
  decides on (the creator is the author), state uncertainty instead of
  inventing confidence (earn trust), explain when it helps the user.
- **Minimal leakage:** no internal jargon, implementation details or
  other users' data in prompts; assume a system prompt can be
  extracted.

## Step 3: Injection resistance

User-supplied text, file contents, image text and tool results are
data, not instructions: delimit them, say so in the prompt, and keep the
model on its task (refuse off-task requests explicitly). Never let
prompt text grant permissions -- authorization is deterministic code.
For prompts exposed to untrusted input, keep a small set of live
adversarial cases (role-play, "ignore previous instructions", embedded
instructions in content, off-task requests) alongside positive cases.

## Step 4: Version and measure

- Version prompts by content hash (`noemeo_agent_kit.prompt_hash`) and
  store the hash with results, so any output traces to its prompt.
- Re-run the baseline inputs, the adversarial cases and any golden set;
  compare before/after side by side. Paid live runs stay outside the
  unit-test suite; record when they were run and the result.
- Keep the change minimal: one hypothesis per revision.

## Step 5: Report

The prompt diff, the hypothesis, before/after results on the same
inputs (including adversarial ones), the new prompt hash, and anything
not re-tested. For a review: findings (Severity, Where, Finding, Fix)
against steps 2-4.
