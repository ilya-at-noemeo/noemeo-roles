# noemeo-roles

**Governed, provider-independent AI-assisted software engineering.**

Coding agents can implement features, write tests, inspect repositories
and review changes. None of those capabilities, by itself, constitutes a
software engineering process.

**The engineering process governs the agents; the agent provider does
not define the engineering process.**

`noemeo-roles` separates the *engineering contract* -- who is
responsible for what, what evidence is required, and when work may
proceed -- from the *machinery* that executes it. It currently works
with **Claude Code and Codex** through shared roles, skills and hook
scripts, and both follow the same
[working agreement](roles/working-agreement.md). The principles behind
it, the lifecycle it aims for and what is still a goal are in
[docs/principles.md](docs/principles.md).

## What it does today

### Enforced by hooks

Both integrations run the same core hook scripts on their lifecycle
events. Once installed, enabled and, for Codex, trusted, these checks
run whether or not the model chooses to perform them:

- **Review gate** (PreToolUse + SubagentStop): no `gh pr create` until
  `noemeo-code-reviewer`, a separate agent that doesn't share the
  author's reasoning, has approved the change as it is now. Any later
  edit voids the approval. The same hook checks the reviewed change
  under both tools.
- **Guard** (PreToolUse): denies destructive git and file commands and
  access to secrets; optionally requires a named AWS profile.
- **Ruff** (PostToolUse) and **tests before stop** (Stop), in repos
  that opt in: lint fixed on every Python edit, and a failing test run
  blocks the first attempt to end a turn and hands the failure back.
- **Session context** (SessionStart): branch, uncommitted files, recent
  commits, open issues, last failing test run, and the working
  agreement.
- **Agent usage log** (Claude Code only, SubagentStop): one JSON line
  per subagent run. Codex usage logging is not implemented.

These hold only where the hooks are installed and active, and only for
the operations they intercept. Details, per-repo configuration
(`.claude/noemeo-guard.json`) and limits: [docs/hooks.md](docs/hooks.md).

### Required by roles and skills, not mechanically checked

- **Tests that prove they can fail.** The test engineer writes tests
  only, and must show each one going red when the behaviour it pins is
  broken.
- **Measured, not assumed.** Prompt and model work starts from a
  measured baseline and reports before-and-after evidence.
- **Separate responsibilities.** The author never grades its own work,
  the test engineer never edits product code, the reviewer reports but
  never fixes. Without them, one generalist agent writes, tests and
  approves its own change, on generic defaults. In Claude Code the
  reviewer has no Edit or Write tools, though it keeps Bash; under
  Codex it inherits the session's permissions. These limits rest on
  the roles.

## Working with Claude Code and Codex

Start a task in either tool and continue it in the other. Both read the
same role definitions, skills and repository rules; Codex's adapter runs
the same core hook scripts as the Claude Code plugin. The shared working
agreement covers picking up work and leaving a handoff, so the branch,
files, checks and next action carry the task between sessions. Private
chat history does not transfer between tools.

Set up the [Claude Code plugin](docs/plugin.md) and the
[Codex adapter](docs/codex.md) for the tools you use. Hooks must be
installed and active; Codex also requires the user to trust their
definitions before they run. The Codex setup guide documents the
remaining tool-specific differences and activation checks.

## Contract, execution and machinery

| Layer | Owns | Examples |
| --- | --- | --- |
| **Engineering governance** | Standards, responsibilities, boundaries, acceptance and evidence expectations | [Working agreement](roles/working-agreement.md), `roles/`, product-specific rules |
| **Execution workflow** | Turning roles into repeatable tasks, checks, gates and handoffs | `skills/`, `agents/`, `hooks/` |
| **Provider machinery** | Tool-specific agent invocation and lifecycle integration | [Claude Code plugin](docs/plugin.md), [Codex adapter](docs/codex.md) |

A **role** writes down one kind of work: scope, out of scope, hard
limits where needed, judgment, and handoffs. **Skills and agents** carry
roles out; **hooks** enforce the parts that mustn't depend on the
model. Because a role is plain Markdown, any person or model can follow
it, and it outlives the tool: when either tool changes, or a person
takes on the work, the role stays and only the wiring changes.

A role that nothing loads is just documentation, so a test checks that
every file in `roles/` is read by at least one skill or agent.

## Repository organization

| Kind | What it is | Read by | Where |
| --- | --- | --- | --- |
| **Roles** | Normative scope, boundaries, judgment and handoffs | Agents and people performing the work | `roles/` |
| **Tool integration** | Shared workflows and checks, Claude Code plugin and Codex adapter | Claude Code and Codex | `skills/`, `agents/`, `hooks/`, `codex/` (tested in `tests/`) |
| **Documentation** | How the system works and how to use it | People | `README.md`, `docs/` |

Role files hold rules only, because agents load them into context;
explanation goes in `docs/`, where no agent pays for it.

This repository is **generic**: it does not name or link a specific
product or product repository. Product-specific rules live in each
product's own `CLAUDE.md` and `docs/`; skills read both. Everything is
grounded in `noemeo-foundation` (private), the company-wide mission,
principles and ethics. Anything here that contradicts the foundation is
wrong, not the foundation.

## Roles

```text
roles/
  working-agreement.md    -- rules every role follows: sources, safety, review, handoff
  product/
    vision.md             -- product vision & positioning
    product-management.md -- backlog, milestones, requirements, priorities
    ux-design.md          -- flows, visual design, accessibility, AI-output presentation
  engineering/
    architecture.md       -- system design, boundaries, schemas, tech choices
    ai-engineering.md     -- model-backed components: LLMs, prompts, evals, ML
    implementation.md     -- writing code against an agreed architecture
    testing.md            -- verification, edge cases, adversarial review, test suites
  research/
    research.md           -- studies, benchmarks, controlled experiments, write-ups
```

Each role follows the same shape: **Scope**, **Out of scope**, **Hard
limits** (where the role has them), **Judgment lens**, **Grounded in** (how `noemeo-foundation` binds it), and **Hands
off to / receives from**. They're most useful as a lens to ask for
("review this as the testing role would"), and as onboarding text for a
person taking on that kind of work. New roles only when there's a real
need.

## Skills and agents

Both tools use the skills and agent definitions below. Claude Code
loads them through the `noemeo` plugin, installed once at user scope;
Codex loads the same sources through per-checkout adapters. Setup and
updates: [Claude Code](docs/plugin.md), [Codex](docs/codex.md).

| Name | Kind | Use it for |
| --- | --- | --- |
| `noemeo-design-review` | skill | Reviewing a design, plan or diff against settled decisions and the current repo's `CLAUDE.md` |
| `noemeo-llm-engineering` | skill | Designing or reviewing an LLM-backed component: LLM vs. deterministic code, model choice, structured output, client seam, cost/latency, evals |
| `noemeo-prompt-engineering` | skill | Writing, revising or reviewing prompts: measured baseline, provider-aware structure, principles, injection resistance, prompt hashes, before/after evidence |
| `noemeo-ml-engineering` | skill | Classical ML and self-hosted inference: baselines, splits/leakage, reproducible evaluation, serving, drift |
| `noemeo-ux-review` | skill | Usability, WCAG 2.2 AA, visual design and AI-output presentation review with prioritized fixes |
| `noemeo-product-management` | skill | Planning and tracking: sweeping loose commitments into a GitHub-issue backlog, milestones with exit criteria, feature requirements, priority proposals and status -- the owner decides |
| `noemeo-iam-review` | skill | Security review of IAM and CI deploy access: trust/OIDC, least privilege, environment separation, escalation paths, role-assuming workflows |
| `noemeo-backend-architecture` | skill | Designing or reviewing backend systems: data ownership and custody, boundaries, contract-first APIs, failure modes, schemas, security, observability and cost sized to real need |
| `noemeo-research` | skill | Studies of model-backed features: falsifiable claims, prior work, public benchmarks and their terms, controlled runs with validated graders, research notes and publication packages |
| `noemeo-test-engineering` | skill | Designing and building automated tests: the right level per behaviour, hermetic and no paid calls, proving tests can fail, wiring into the repo's checks |
| `noemeo-ship` | skill | Taking a change from request to open PR: plan, branch, implement, tests by `noemeo-test-engineer`, review by `noemeo-code-reviewer` until Ready, then commit, push and PR |
| `noemeo-worktree` | skill | Parallel worktrees ready to work in: outside every repo (no stale `CLAUDE.md` above them), env files copied, dependencies installed so the ruff and test hooks run; removal refuses unsaved work |
| `noemeo-ai-engineer` | agent | Delegating self-contained AI engineering work (LLM/prompt/eval/ML) to Noemeo's AI engineering role in its own context, with measured results -- prompt design, optimization and hardening on a fixed model included (loads `noemeo-prompt-engineering`) |
| `noemeo-backend-architect` | agent | Delegated backend design work in its own context (architecture role): a design doc and its rationale, never product code |
| `noemeo-ux-designer` | agent | Independent UI/UX review in its own context (UX design role). Read-only. |
| `noemeo-product-manager` | agent | Delegated planning work in its own context (product management role): backlog sweeps, milestone readiness, requirements, priority proposals. Never writes to the tracker: returns `gh` commands for the main session to run; never code, never publishes. |
| `noemeo-code-reviewer` | agent | Independent, adversarial review of a change before commit/PR: correctness, security, intent, decisions -- verified by running the repo's checks. Read-only. |
| `noemeo-researcher` | agent | Delegated research in its own context (research role): study plans, runs within an approved budget, write-ups and publication packages. Never changes product code to make a result happen; never submits externally. |
| `noemeo-test-engineer` | agent | Building and maintaining test suites in its own context (testing role, building side): unit, integration, browser and host-SDK tests, each shown to fail. Writes tests only, never product code. |

## Keeping the tools consistent

Change the shared role, skill or hook source rather than maintaining
separate rules for each tool. Claude Code runs an installed copy of
the plugin; Codex reads this checkout through its adapters. After a
source change, update the Claude Code plugin and rerun the Codex
installer as described in their setup guides. The installer's
`--check` mode reports stale generated files and differing installed
copies, helping catch drift before the next task.

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
