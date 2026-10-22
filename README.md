# noemeo-roles

How Noemeo work gets done, shared across every Noemeo repo. Two
things live here:

- **`skills/`, `agents/`** -- reusable procedures and a few agents,
  packaged as a Claude Code plugin (`noemeo`), e.g.
  `noemeo-design-review`, `noemeo-ai-engineer`, `noemeo-code-reviewer`.
- **`product/`, `engineering/`, `research/`** -- role definitions (product
  vision, UX design, architecture, AI engineering, implementation,
  testing, research): scope, judgment and boundaries for a kind of work,
  usable by a human or any LLM.

This repo is **generic**: nothing here names or links a product or
product-specific repo. Product-specific rules live in
each product's own `CLAUDE.md` and `docs/`; skills read both.

Everything is grounded in `noemeo-foundation` (private) -- the
company-wide mission, principles and ethics. Anything here that
contradicts the foundation is wrong, not the foundation.

## Skills and agents (Claude Code plugin)

The repo root is a Claude Code plugin marketplace with one plugin,
`noemeo`: skills in `skills/`, agents in `agents/`. Install once, at user scope,
and the skills are available in every repo:

```bash
claude plugin marketplace add ~/workspace/noemeo/noemeo-roles
claude plugin install noemeo@noemeo-roles --scope user
```

(`/plugin ...` in the terminal CLI does the same; the IDE extension
doesn't have `/plugin`.) After editing a skill or agent, run
`claude plugin update noemeo@noemeo-roles` and start a new session --
the plugin is installed as a copy, not a live link. Validate manifests with
`claude plugin validate .`.

| Name | Kind | Use it for |
| --- | --- | --- |
| `noemeo-design-review` | skill | Reviewing a design, plan or diff against settled decisions and the current repo's `CLAUDE.md` |
| `noemeo-llm-engineering` | skill | Designing or reviewing an LLM-backed component: LLM vs. deterministic code, model choice, structured output, client seam, cost/latency, evals |
| `noemeo-prompt-engineering` | skill | Writing, revising or reviewing prompts: measured baseline, provider-aware structure, principles, injection resistance, prompt hashes, before/after evidence |
| `noemeo-ml-engineering` | skill | Classical ML and self-hosted inference: baselines, splits/leakage, reproducible evaluation, serving, drift |
| `noemeo-ux-review` | skill | Usability, WCAG 2.2 AA, visual design and AI-output presentation review with prioritized fixes |
| `noemeo-iam-review` | skill | Security review of IAM and CI deploy access: trust/OIDC, least privilege, environment separation, escalation paths, role-assuming workflows |
| `noemeo-backend-architecture` | skill | Designing or reviewing backend systems: data ownership and custody, boundaries, contract-first APIs, failure modes, schemas, security, observability and cost sized to real need |
| `noemeo-research` | skill | Studies of model-backed features: falsifiable claims, prior work, public benchmarks and their terms, controlled runs with validated graders, research notes and publication packages |
| `noemeo-test-engineering` | skill | Designing and building automated tests: the right level per behaviour, hermetic and no paid calls, proving tests can fail, wiring into the repo's checks |
| `noemeo-ai-engineer` | agent | Delegating self-contained AI engineering work (LLM/prompt/eval/ML) to Noemeo's AI engineering role in its own context, with measured results -- prompt design, optimization and hardening on a fixed model included (loads `noemeo-prompt-engineering`) |
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
independently. Agents run on the session's model unless their frontmatter sets
`model:` -- `noemeo-test-engineer` and `noemeo-ux-designer` use Sonnet.
Keep role definitions
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
| PreToolUse | `guard.py` | Denies `rm -rf`, force-pushes, `git clean -f`, and Bash or file-tool access to secrets: `.env`/`.env.*` (not `.env.example`), `*.pem`, `.certs/`, `.aws/credentials`. Commit messages and PR bodies that only mention them are allowed. In a repo that lists its AWS profiles, also denies `aws`/`terraform` commands that don't use one. |
| SessionStart | `session_context.sh` | Adds branch, uncommitted files, recent commits, open GitHub issues and the last failing test run to the session. |
| PreToolUse | `review_gate.py` | Before `gh pr create` (or its alias `gh pr new`), denies unless `noemeo-code-reviewer`'s latest review of the change *as it is now* says Ready or Ready with nits; tells Claude to run the reviewer otherwise. Fails closed: a mention counts unless it sits wholly in a heredoc body or quoted string, the command runs no shell, interpreter or other runner (`sh -c`, `python`, `xargs`, `ssh`, `$VAR`, ...) and no `$(`/backtick comes before it -- so a commit message naming it passes, anything else is denied. |
| SubagentStop | `review_record.py` | When `noemeo-code-reviewer` finishes, records its verdict against a fingerprint of the repo it names: the content of every file changed since the merge-base with the PR base, untracked files included. It records against the repo's default bases (`origin/HEAD`, `origin/dev`, `origin/main`) and any remote branch the branch is stacked on (in its history, not yet in a default base), so a PR targeting another open branch can pass the gate. A stacked base that has gained commits since isn't in the branch's history: rebase onto it, then review. Committing reviewed changes keeps the fingerprint; any further edit voids it. Records live in the repo's git directory (`noemeo-reviews.jsonl`), never in the tree. Its matcher is the regex `(^\|:)noemeo-code-reviewer$`: a plugin agent's type is scoped (`noemeo:noemeo-code-reviewer`), and a matcher of only letters and hyphens is compared exactly, so the plain name never fires. |
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

A repo that works against an AWS account names that account's profiles
from `~/.aws/config` there too. The guard then denies an `aws` or
`terraform` command that can reach AWS unless it uses one of them
(`--profile`, an `AWS_PROFILE=` prefix, or `AWS_PROFILE` in the
session), so nothing falls back to the default credentials, which on a
developer's own machine may be another account. Pair it with
`"env": {"AWS_PROFILE": "<profile>"}` in the repo's
`.claude/settings.json`, so scripts and SDKs default to the right
account too:

```json
{ "aws_profiles": ["acme-dev", "acme-admin"] }
```

The guard reads command text, not intent, so it errs toward denying:
a heredoc that feeds a script and merely *mentions* a blocked command
or secret is denied too. Write such text with the file tools instead.

Tool-specific hooks for other stacks (`terraform fmt`, say) get added
here once a repo actually needs one. Review or disable
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

## License

Licensed under the [Apache License, Version 2.0](LICENSE).
