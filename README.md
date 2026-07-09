# noemeo-roles

Definitions of Noemeo's internal working roles -- analogous to CTO, Staff
Engineer, Product Manager, QA Lead -- meant to be read by an LLM (any
provider) that has been asked to act in that capacity for a conversation or
a thread.

## What this repo is, and isn't

**This repo defines roles. It does not implement them.** No tool lists, no
model choices, no subagent frontmatter, no provider-specific mechanics.
Deliberately -- the invocation mechanism (a Claude Code subagent, a plain
"read this file and act accordingly," something else) is expected to change
over time and shouldn't be locked into any one provider's framework. A role
document should be equally usable by pasting it into any capable LLM's
context.

**A role is not a persona detached from the company.** Just as a real
employee is expected to act within their company's values regardless of
their specific job function, every role here is explicitly grounded in
[`noemeo-foundation`](https://github.com/ilya-at-noemeo/noemeo-foundation)
-- the company-wide mission, principles, and ethics. A role document that
contradicts the foundation is wrong, not the foundation.

## Practical use

The intended workflow is parallel, role-dedicated conversation threads --
one thread stays anchored to the architecture role, another to
implementation, another to testing, etc. -- rather than one thread
switching personas mid-conversation. Each role document is written to be
self-contained enough to anchor a fresh thread cold: point an assistant at
the relevant `noemeo-foundation` documents and at the specific product's
own docs (e.g. `noemeo-backend/docs/`) as needed, don't assume prior
conversation history.

## Structure

```text
product/
  vision.md          -- product vision & positioning
engineering/
  architecture.md     -- system design, boundaries, schemas, tech choices
  implementation.md    -- writing code against an agreed architecture
  testing.md            -- verification, edge cases, adversarial review
```

Roles are grouped by department. Only the roles with active, current use
are defined so far -- see the individual documents' "Hands off to /
receives from" sections for how they relate to each other. More
departments (marketing, operations) and roles may be added later, but only
once there's a real need for them, not speculatively.

## Document shape

Each role document follows the same shape:

- **Scope** -- what this role is responsible for.
- **Out of scope** -- what it explicitly does not do.
- **Judgment lens** -- how this role weighs tradeoffs, distinct from other
  roles.
- **Grounded in** -- how it's bound by `noemeo-foundation`'s mission,
  principles, and ethics, not just generic competence for the job.
- **Hands off to / receives from** -- its relationship to adjacent roles.
