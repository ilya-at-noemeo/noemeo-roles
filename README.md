# noemeo-roles

How Noemeo work gets done, shared across every Noemeo repo. Three
things live here:

- **`decisions/`** -- the decision log: settled, generic decisions
  (driver/agent boundary, repo ownership, environments, no VPC...)
  that designs and changes are reviewed against. Start here.
- **`skills/`** -- reusable procedures, packaged as a Claude Code plugin
  (`noemeo`), e.g. `noemeo-design-review`.
- **`product/`, `engineering/`** -- role definitions (product vision,
  architecture, implementation, testing): scope, judgment and
  boundaries for a kind of work, usable by a human or any LLM.

This repo is **generic**: nothing here names or links a product or
product-specific repo (decision 0004). Product-specific rules live in
each product's own `CLAUDE.md` and `docs/`; skills read both.

Everything is grounded in
[`noemeo-foundation`](https://github.com/ilya-at-noemeo/noemeo-foundation)
-- the company-wide mission, principles and ethics. Anything here that
contradicts the foundation is wrong, not the foundation.

## Decision log

See [`decisions/README.md`](decisions/README.md) for the format and
index. One decision per numbered file, each ending in concrete
**Review checks**. To change a decision, add a new one that supersedes
it. Product-specific decisions don't go here.

## Skills (Claude Code plugin)

The repo root is a Claude Code plugin marketplace with one plugin,
`noemeo`, whose skills are in `skills/`. Install once, at user scope,
and the skills are available in every repo:

```text
/plugin marketplace add ~/workspace/noemeo/noemeo-roles
/plugin install noemeo@noemeo-roles
```

After editing a skill or decision, run `/plugin update noemeo` (or
`claude plugin update noemeo`) so the installed copy picks it up -- the
plugin is installed as a copy, not a live link. Validate manifests with
`claude plugin validate .`.

| Skill | Use it for |
| --- | --- |
| `noemeo-design-review` | Reviewing a design, plan or diff against the decision log and the current repo's `CLAUDE.md` |

Skills use the open `SKILL.md` format (name + description frontmatter,
plain Markdown body), readable by people and by other agent tools.
Provider-specific agent definitions (subagent personas with tool
lists) don't belong here; role definitions stay provider-neutral.

For general bug-hunting, security and cleanup, use Claude Code's
built-ins rather than duplicating them: `/code-review`,
`/security-review`, `/simplify`.

## Role definitions

```text
product/
  vision.md          -- product vision & positioning
engineering/
  architecture.md    -- system design, boundaries, schemas, tech choices
  implementation.md  -- writing code against an agreed architecture
  testing.md         -- verification, edge cases, adversarial review
```

Each follows the same shape: **Scope**, **Out of scope**, **Judgment
lens**, **Grounded in** (how `noemeo-foundation` binds it), and **Hands
off to / receives from**. They're most useful as a lens to ask for
("review this as the testing role would"), and as onboarding text for a
person taking on that kind of work. New roles only when there's a real
need.

## Open items: GitHub issues

Something noticed now that needs attention later, or from a different
kind of work, goes in a **GitHub issue in this repo**, labeled
`role:<name>` (`role:product-vision`, `role:architecture`,
`role:implementation`, `role:testing`). State what needs attention and
why, enough for someone picking it up cold. Issues are open items;
once resolved, any durable decision that came out of one goes in
`decisions/`, referencing the issue number.
