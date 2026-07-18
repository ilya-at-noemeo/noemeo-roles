# Drivers can differ; the driver/agent contract can't

**Decision** (2026-07-18, `noemeo-backend`, while building `image_worth_scorer`'s
Lambda driver): every agent module (`graph.py`/`schema.py`/`prompts.py`
under `agents/<name>/`) stays a pure Python component -- explicit
parameters in, typed Pydantic models out, never reading env vars, never
aware of its invocation transport. Everything transport- and
environment-specific belongs in a **driver** (`lambda_handler.py`, an
eventual FastAPI route, etc.), whose job is always: read config from the
environment → translate transport-specific input into the agent's plain
parameters → call the agent → translate the result back into the
transport's response shape.

## Why this came up

Prompted by a direct question: "should this Lambda be generic?" The
instinct behind asking was reasonable (DRY, consistency) but the answer
was no, *not the driver's code* -- only one agent existed
(`image_worth_scorer`, a pure function with no external dependencies), and
the next ones won't share its shape: Tier 2 needs a database lookup for
`project_context`; the edit-suggestion agent is a loop, not a single
request/response; the story/context agent streams via a Function URL, not
a plain Lambda invocation at all. Genericizing the driver *implementation*
now would have been shaped by the simplest possible case and likely wrong
for the next one -- premature abstraction.

What *should* generalize, and now does (`noemeo-backend/docs/architecture.md`,
"Driver / agent boundary"): the **responsibility split** between driver
and agent, not the code. Every future driver -- however different its
internals -- must leave the agent itself untouched by transport or config
concerns, and every agent must remain callable directly with no driver at
all (already true of every test in the codebase).

## The general lesson

When something varies (implementation) *and* something should stay fixed
(the contract/responsibility split) are both present in the same
decision, don't let "should we genericize?" collapse them into one
question. Making the varying part generic too early risks building the
wrong abstraction from a single data point. Writing the fixed part down
explicitly, even while every instance's code differs, is what actually
prevents drift.

**How to apply:** when a new driver (or any new instance of a repeated
pattern) is being built, check `noemeo-backend/docs/architecture.md`'s
"Driver / agent boundary" section for the contract before writing it --
don't re-derive or accidentally violate it by putting scoring/generation
logic in the driver, or transport/config logic in the agent.
