# noemeo-roles

Definitions of Noemeo's internal working roles -- analogous to CTO, Staff
Engineer, Product Manager, QA Lead. **A role can be filled by a human or by
an AI, or by both over time** -- everything in this repo, including
accumulated knowledge (see below), is written to be equally usable for
onboarding a human into the role and for briefing an LLM (any provider)
asked to act in that capacity.

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

## Persistent, role-specific knowledge

A role definition (`architecture.md`) is deliberately static -- scope,
judgment lens, boundaries, rarely changing. That's not enough on its own:
a role should get *better* at its job over time, accumulating decisions,
rationale, and learnings from actually doing the work, the same way a real
employee does. Each role that has this enabled gets a `knowledge/`
directory next to its definition file:

```text
engineering/
  architecture.md
  architecture/
    knowledge/
      index.md        -- topic index, one line per entry
      <topic>.md       -- the actual accumulated content
```

Plain markdown, human-readable, no embeddings-only or opaque storage --
the same constraint that applies to the role definitions applies here,
since a human onboarding into a role needs to be able to read it directly.

Company-wide (cross-role) accumulated knowledge is a related but separate
concern, intentionally not designed yet -- starting with role-specific
knowledge only, proven on one role before generalizing.

## Cross-role and deferred communication

When whoever is filling a role (human or AI) notices something that needs
attention from a *different* role, or from the *same* role but *later*
(not part of the current thread's work), the mechanism is a **GitHub
issue in this repo** -- not an ad-hoc note left in a chat transcript that
nobody will see again.

- Label the issue `role:<name>` for whichever role should address it
  (`role:product-vision`, `role:architecture`, `role:implementation`,
  `role:testing`). Apply more than one label if it's relevant to several
  roles.
- State plainly what needs attention and why -- enough for whoever picks
  up that role cold, human or AI, to act on it without needing the
  original conversation's context.
- Whoever assumes a role should check open issues labeled for that role
  as part of picking up the work, the same way a real employee checks
  their queue before starting the day.

This is deliberately separate from `knowledge/`: **issues are open items
awaiting action; `knowledge/` is settled, accumulated understanding.**
Once an issue is resolved, whatever durable learning came out of it (if
any) belongs in `knowledge/`, not left sitting in a closed issue.

## Structure

```text
product/
  vision.md          -- product vision & positioning
engineering/
  architecture.md     -- system design, boundaries, schemas, tech choices
  architecture/
    knowledge/          -- accumulated architecture-role knowledge
  implementation.md    -- writing code against an agreed architecture
  testing.md            -- verification, edge cases, adversarial review
```

Roles are grouped by department. Only the roles with active, current use
are defined so far -- see the individual documents' "Hands off to /
receives from" sections for how they relate to each other. More
departments (marketing, operations) and roles may be added later, but only
once there's a real need for them, not speculatively. Likewise,
`knowledge/` is scaffolded for the architecture role only for now --
proving the pattern before extending it to the others.

## Document shape

Each role document follows the same shape:

- **Scope** -- what this role is responsible for.
- **Out of scope** -- what it explicitly does not do.
- **Judgment lens** -- how this role weighs tradeoffs, distinct from other
  roles.
- **Grounded in** -- how it's bound by `noemeo-foundation`'s mission,
  principles, and ethics, not just generic competence for the job.
- **Hands off to / receives from** -- its relationship to adjacent roles.
