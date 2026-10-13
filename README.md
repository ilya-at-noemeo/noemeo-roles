# noemeo-roles

How Noemeo work gets done, shared across every Noemeo repo. Three
things live here:

- **`decisions/`** -- the decision log: settled, generic decisions
  (driver/agent boundary, repo ownership, environments, no VPC...)
  that designs and changes are reviewed against. Start here.
- **`skills/`, `agents/`** -- reusable procedures and a few agents,
  packaged as a Claude Code plugin (`noemeo`), e.g.
  `noemeo-design-review`, `noemeo-ai-engineer`, `noemeo-code-reviewer`.
- **`product/`, `engineering/`, `research/`** -- role definitions (product
  vision, UX design, architecture, AI engineering, implementation,
  testing, research): scope, judgment and boundaries for a kind of work,
  usable by a human or any LLM.

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
| `noemeo-llm-engineering` | skill | Designing or reviewing an LLM-backed component: LLM vs. deterministic code, model choice, structured output, client seam, cost/latency, evals |
| `noemeo-prompt-engineering` | skill | Writing, revising or reviewing prompts: measured baseline, provider-aware structure, principles, injection resistance, prompt hashes, before/after evidence |
| `noemeo-ml-engineering` | skill | Classical ML and self-hosted inference: baselines, splits/leakage, reproducible evaluation, serving, drift |
| `noemeo-ux-review` | skill | Usability, WCAG 2.2 AA, visual design and AI-output presentation review with prioritized fixes |
| `noemeo-iam-review` | skill | Security review of IAM and CI deploy access: trust/OIDC, least privilege, environment separation, escalation paths, role-assuming workflows |
| `noemeo-backend-architecture` | skill | Designing or reviewing backend systems: data ownership and custody, boundaries, contract-first APIs, failure modes, schemas, security, observability and cost sized to real need |
| `noemeo-research` | skill | Studies of model-backed features: falsifiable claims, prior work, public benchmarks and their terms, controlled runs with validated graders, research notes and publication packages |
| `noemeo-test-engineering` | skill | Designing and building automated tests: the right level per behaviour, hermetic and no paid calls, proving tests can fail, wiring into the repo's checks |
| `noemeo-ai-engineer` | agent | Delegating self-contained AI engineering work (LLM/prompt/eval/ML) to Noemeo's AI engineering role in its own context, with measured results |
| `noemeo-prompt-engineer` | agent | Delegated prompt design/optimization/hardening on a fixed model, with before/after numbers (AI engineering role) |
| `noemeo-backend-architect` | agent | Delegated backend design work in its own context (architecture role): a design doc and its rationale, never product code |
| `noemeo-ux-designer` | agent | Independent UI/UX review in its own context (UX design role). Read-only. |
| `noemeo-code-reviewer` | agent | Independent, adversarial review of a change before commit/PR: correctness, security, intent, decisions -- verified by running the repo's checks. Read-only. |
| `noemeo-researcher` | agent | Delegated research in its own context (research role): study plans, runs within an approved budget, write-ups and publication packages. Never changes product code to make a result happen; never submits externally. |
| `noemeo-test-engineer` | agent | Building and maintaining test suites in its own context (testing role, building side): unit, integration, browser and host-SDK tests, each shown to fail. Writes tests only, never product code. |

Skills use the open `SKILL.md` format (name + description frontmatter,
plain Markdown body), readable by people and by other agent tools.
**Agents only when a separate context is the point** -- a reviewer that
must not share the author's reasoning, or a self-contained piece of a
role's work worth delegating. Each is a thin adapter for a role
definition here (`noemeo-code-reviewer` fills `engineering/testing.md`,
`noemeo-ai-engineer` fills `engineering/ai-engineering.md`,
`noemeo-backend-architect` fills `engineering/architecture.md`,
`noemeo-researcher` fills `research/research.md`,
`noemeo-ux-designer` fills `product/ux-design.md`): it loads the
role and the skills rather than restating them. `noemeo-test-engineer`
fills the same testing role as `noemeo-code-reviewer`, from the
building side: one writes the tests, the other checks the change
independently. Keep role definitions
provider-neutral, and adapt third-party agent templates this way instead
of installing them as-is (they reference agents and stacks that don't
exist here).

For general bug-hunting, security and cleanup, use Claude Code's
built-ins rather than duplicating them: `/code-review`,
`/security-review`, `/simplify`.

## Hooks (Claude Code plugin)

The same plugin ships hooks (`hooks/hooks.json`), so they run in every
repo it's enabled in. Guarantees, not suggestions: each runs on its
lifecycle event whatever the model decides.

| Event | Hook | Does |
| --- | --- | --- |
| PreToolUse | `guard.py` | Denies `rm -rf`, force-pushes, `git clean -f`, and Bash or file-tool access to secrets: `.env`/`.env.*` (not `.env.example`), `*.pem`, `.certs/`, `.aws/credentials`. Commit messages and PR bodies that only mention them are allowed. |
| SessionStart | `session_context.sh` | Adds branch, uncommitted files, recent commits, open GitHub issues and the last failing test run to the session. |
| PostToolUse | `ruff_touched_file.sh` | `ruff check --fix` then `ruff format` on each edited `.py` file; unfixable lint goes back to Claude. |
| Stop | `stop_tests.py` | `pytest -x -q`; a failure blocks the turn from ending and is handed back. Skipped when the tree is unchanged since the last green run. |

A repo opts in to the last two by having what they need, nothing else:

- **ruff:** a `[tool.ruff]` table in its `pyproject.toml` and ruff in its
  `.venv` (a dev dependency). Without both, edits aren't touched -- so
  adopting it is a deliberate one-time format commit, not drift.
- **tests:** pytest in its `.venv`.

A repo with secrets of its own lists them in `.claude/noemeo-guard.json`,
as literal names or `*.<ext>`:

```json
{ "secrets": [".my_tokens.json", "*.p12"] }
```

The guard reads command text, not intent, so it errs toward denying:
a heredoc that feeds a script and merely *mentions* a blocked command
or secret is denied too. Write such text with the file tools instead.

Tool-specific hooks for other stacks (`terraform fmt`, say) get added
here once a repo actually needs one (decision 0003). Review or disable
hooks with `/hooks`.

## Role definitions

```text
product/
  vision.md          -- product vision & positioning
  ux-design.md       -- flows, visual design, accessibility, AI-output presentation
engineering/
  architecture.md    -- system design, boundaries, schemas, tech choices
  ai-engineering.md  -- model-backed components: LLMs, prompts, evals, ML
  implementation.md  -- writing code against an agreed architecture
  testing.md         -- verification, edge cases, adversarial review, test suites
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
`role:ux-design`, `role:ai-engineering`, `role:implementation`,
`role:testing`). State what needs attention and
why, enough for someone picking it up cold. Issues are open items;
once resolved, any durable decision that came out of one goes in
`decisions/`, referencing the issue number.
