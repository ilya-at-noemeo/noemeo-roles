---
name: noemeo-prompt-engineering
description: Writes, revises or reviews prompts (system prompts, instructions, few-shot examples, output schemas, agent/tool instructions, Agent Skill instructions) for Noemeo LLM components on an already-chosen model -- requirements and a measured baseline first, structure tuned to the target model's provider guidance, Noemeo's principles, injection resistance, prompt-hash versioning, and eval-driven iteration with before/after numbers. Use when creating or changing a prompt, when output quality, format or cost regresses, or when asked to review or harden a prompt.
---

# Noemeo prompt engineering

Procedure for the AI engineering role (`../../roles/engineering/ai-engineering.md`
relative to this skill's base directory) for prompt text on an
already-chosen model. Model/provider choice, schema plumbing and agent
design: `noemeo-llm-engineering`.

## Step 1: Requirements and baseline

Ask only for what's missing:

1. **Use case and consumer** -- who or what reads the output.
2. **Target model and provider** -- prompting guidance differs by
   model family and version; read that provider's current prompting
   guide instead of applying one vendor's tricks to another's model.
3. **Baseline** -- the current prompt, its output on 5-10+ real inputs,
   and where available quality, token usage and latency.
4. **Success criteria** -- numeric targets agreed with the user, not
   universal thresholds.
5. **Constraints** -- the repo's `CLAUDE.md` and `docs/decisions/`
   (what may be sent, what may be logged), injection exposure.

Run the current prompt on the inputs before changing anything -- a
change without a baseline can't be shown to help. Check where prompt
text lives (some prompts load from shared files rather than Python
constants -- edit the source, don't fork it).

## Step 2: Structure

- **System vs. user turn:** stable role and instructions in the system
  prompt; variable input in the user turn.
- **Order:** long reference material first, instructions and the
  question last; stable text before variable text (helps prompt
  caching on providers that support it).
- **Delimit sections** (instructions, context, documents, examples,
  user input) with clear markers -- XML-style tags or markdown headings,
  whichever the target model's guidance prefers.
- **Plain, calm instructions:** say what to do and why; one idea per
  instruction; no contradictions with the schema. Avoid ALL-CAPS and
  "you MUST/NEVER EVER" escalation -- on current models it tends to
  cause over-triggering rather than compliance.
- **Examples:** 2-5 varied ones, only where they fix a real ambiguity in
  format or tone; vary surface features so they aren't copied.
- **Reasoning:** for multi-step judgment, ask for step-by-step
  reasoning or use the model's reasoning setting (e.g. OpenAI
  `reasoning_effort`, Claude extended thinking/`effort`) -- confirm what
  the target model version supports and what it costs; skip for simple
  extraction or classification.
- **Output:** prefer schema-constrained structured output over prompted
  formatting; the prompt explains what fields *mean*, not JSON syntax.
- **Agent/tool prompts:** state when each tool should and shouldn't be
  used, limits on autonomy, confirmation before destructive actions,
  and what to do on tool errors -- not "use tools wisely".
- **Noemeo's principles:** gather intent before generating (reveal
  before generate), frame output as suggestions the person decides on
  (the creator is the author), state uncertainty instead of inventing
  confidence (earn trust), explain when it helps the user.
- **Minimal leakage:** no internal jargon, implementation details or
  other users' data; assume a system prompt can be extracted.

## Step 3: Injection resistance

User-supplied text, file contents, image text and tool results are
data, not instructions: wrap them in labelled delimiters, say so in the
prompt, and keep the model on task (refuse off-task requests
explicitly). Never let prompt text grant permissions -- authorization
is deterministic code. For prompts exposed to untrusted input, keep
live adversarial cases (role-play, "ignore previous instructions",
instructions embedded in content, off-task requests) alongside positive
cases.

## Step 4: Measure and version

- Run the baseline inputs, a held-out golden set, edge and adversarial
  cases; compare variants side by side on the **same** inputs.
- **Consistency:** run the same input a few times; unstable output is a
  finding.
- **Cost-benefit:** report quality gained against tokens and latency
  added; a longer prompt has to earn its tokens.
- LLM-as-judge only after checking its agreement with human labels.
- Version by content hash (`noemeo_agent_kit.prompt_hash`) and record
  the hash with every result. Log prompt hash, model, token usage and
  latency -- **not** prompt inputs or outputs, unless the product's
  rules explicitly allow it (user content is often not loggable).
- Paid live runs stay outside the unit-test suite; record when they ran.
- One hypothesis per revision; iterate on measured results.

## Step 5: Report

Lead with measured numbers, e.g. "8 variants on a 40-input set: the
restructured prompt with 3 examples moved tier agreement from 62% to
78% and cut input tokens 18%." Then: the prompt diff and hypothesis,
before/after on the same inputs (adversarial included), consistency,
cost/latency change, the new prompt hash, and what wasn't re-tested.
For a review: findings (Severity, Where, Finding, Fix) against steps
1-4.

Partly adapted from the community `ai-specialists/prompt-engineer`
template (claude-code-templates), made provider-neutral.
