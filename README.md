# noemeo-roles

How Noemeo work gets done, shared across every Noemeo repo. Three
things live here:

- **`decisions/`** -- the decision log: settled, generic decisions
  (driver/agent boundary, repo ownership, environments, no VPC...)
  that designs and changes are reviewed against. Start here.
- **`skills/`, `agents/`** -- reusable procedures and a few agents,
  packaged as a Claude Code plugin (`noemeo`), e.g.
  `noemeo-design-review`, `noemeo-code-reviewer`.
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

## Skills and agents (Claude Code plugin)

The repo root is a Claude Code plugin marketplace with one plugin,
`noemeo`: skills in `skills/`, agents in `agents/`. Install once, at user scope,
and the skills are available in every repo:

```bash
claude plugin marketplace add ~/workspace/noemeo/noemeo-roles
claude plugin install noemeo@noemeo-roles --scope user
```

(`/plugin ...` in the terminal CLI does the same; the IDE extension
doesn't have `/plugin`.) After editing a skill, agent or decision, run
`claude plugin update noemeo@noemeo-roles` and start a new session --
the plugin is installed as a copy, not a live link. Validate manifests with
`claude plugin validate .`.

| Name | Kind | Use it for |
| --- | --- | --- |
| `noemeo-design-review` | skill | Reviewing a design, plan or diff against the decision logs and the current repo's `CLAUDE.md` |
| `noemeo-iam-review` | skill | Security review of IAM and CI deploy access: trust/OIDC, least privilege, environment separation, escalation paths, role-assuming workflows |
| `noemeo-code-reviewer` | agent | Independent, adversarial review of a change before commit/PR: correctness, security, intent, decisions -- verified by running the repo's checks. Read-only. |

Skills use the open `SKILL.md` format (name + description frontmatter,
plain Markdown body), readable by people and by other agent tools.
**Agents only when a separate context is the point** -- e.g. a reviewer
that must not share the author's reasoning. Each is a thin adapter for
a role definition here (`noemeo-code-reviewer` fills
`engineering/testing.md`); keep the two in sync, and keep role
definitions themselves provider-neutral.

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
