---
name: noemeo-security-review
description: Security review of application code in Noemeo repos -- local scanners (ruff's bandit rules, Semgrep, osv-scanner/pip-audit, gitleaks, zizmor, trivy) triaged by hand, then a threat checklist for data custody, local servers, untrusted input reaching dangerous calls, LLM prompt injection, secrets, cloud endpoints and webhooks, supply chain and app distribution. Use when asked for a security review or audit of a change or a whole repo, when a change touches a server route, auth, credentials, subprocess/file/SQL handling, dependencies, GitHub workflows or anything that sends data off the machine, or before a release. IAM and deploy access go to noemeo-iam-review.
---

# Noemeo security review

Finds ways the code can be made to do what it shouldn't: leak data,
run attacker input, or trust what it can't. Scanners find leads; you
decide which are real. Report only; never edit or install anything.

Complements `noemeo-iam-review` (access in depth: invoke it, don't
duplicate it, when IAM or role-assuming workflows are in scope) and
`noemeo-design-review` (all decisions), and `/security-review` (a
general diff read without tools or Noemeo's rules).

## Step 1: Mode and scope

- **Change** (default; what `noemeo-code-reviewer` asks for): the
  target named in the request, else uncommitted changes, else the
  branch against its base (`dev` in infra repos, `main` elsewhere).
  Scan the changed files, plus any lockfile or workflow the change
  touches.
- **System** (when asked for an audit, or before a release): the whole
  repo. Map its entry points first -- servers and routes, CLIs, plugin
  commands, Lambda handlers, webhooks, workflows -- and what each
  accepts from outside.

## Step 2: Load the rules

Read the generic decisions in `../noemeo-foundation/decisions/` from
the repo root (a sibling checkout; in a worktree, find it through
`git rev-parse --git-common-dir`), the repo's `CLAUDE.md` and its
`docs/decisions/`. They say where data may go (custody), what may run
in the cloud and what the repo treats as untrusted. If foundation
isn't there, say so rather than citing decisions from memory.

## Step 3: Scan

Run each tool that applies, scoped as in step 1 (pass paths in change
mode; only paths that exist, or Semgrep and zizmor fail the whole
run). Use the repo's own ruff (its runner, or `.venv/bin/ruff`). Check
`command -v` first; a missing tool goes under **Not checked** with its
install command. Never install it yourself.

Rows marked *network* make the lookups listed below, which the
working agreement exempts from approval. Skip them only if the request
forbids network use or you're offline, and list them under **Not
checked**.

| Applies to | Command |
|---|---|
| Python | `ruff check --select S --output-format concise <paths>` |
| Python, JS, others (*network*) | `semgrep scan --metrics off --config p/python --config p/owasp-top-ten <paths>` (add `p/javascript` etc. per language) |
| Lockfiles (*network*) | `osv-scanner scan source --format json -L <lockfile>` per lockfile: the changed ones in change mode, those `git ls-files` lists in system mode (`-r .` also walks `.venv` and `node_modules`). Group the result by package: advisory count, highest severity, fixed version, dependency group. "No package sources found" means nothing to scan |
| Git history | `gitleaks git -v --redact --no-banner --log-opts="<base>..HEAD"`; system mode: full history (`-v` gives file and line) |
| Uncommitted files | `gitleaks dir -v --redact --no-banner <file>`, once per changed tracked file, skipping guard-listed files. Never more than one path: given several, gitleaks ignores them and scans the whole working tree, secret files included |
| `.github/workflows/` | `zizmor --offline .github/workflows`; offline skips its online audits (impostor commits, known-vulnerable actions): list them under **Not checked** |
| Terraform, Dockerfiles (*network*) | `trivy config <dir>`; offline, `trivy config --skip-check-update <dir>` works only if its check bundle is already cached |
| A built macOS app (only if named) | `codesign --verify --strict --deep -vv <app>`, `codesign -d --entitlements - <app>`, `spctl -a -t exec -vv <app>` |

Network lookups, the only ones allowed: Semgrep downloads its
registry rules (always with `--metrics off`; never `--config auto`,
`semgrep login` or `semgrep ci`), trivy downloads its check bundle,
and osv-scanner sends package names and versions to OSV and Google's
deps.dev. Never source code, scan results or an upload to a scanner's
service.

Secrets: always `--redact`, and never scan `.env` or other files the
guard config lists. Report where a secret is, never its value.

## Step 4: Triage

For every scanner hit, read the code path: where does the input come
from, and can someone outside reach it? Keep it only with a concrete
abuse path (foothold -> action -> impact). Drop false positives, but
count them per rule with a one-line reason. A suppression in the code
(`# noqa: S…`, `nosemgrep`) needs a stated reason; one without is a
Low finding. A vulnerable dependency matters only if the vulnerable
function or feature is reachable; find where the code calls it (a
parser that only reads the app's own bundled files isn't parsing
attacker input) and say whether it is. A dependency group of `dev`
isn't proof: the same package may also be a runtime dependency.

No hit isn't clean: lockfile scanners don't see native libraries
bundled inside packages (a compiled parser or decoder shipped in a
wheel). Where untrusted input reaches one, name it and its version
under **Not checked**.

## Step 5: Threat checklist

Work through [`references/threat-checklist.md`](references/threat-checklist.md):
every section the scope touches in change mode, all of it in system
mode. Scanners don't see custody, local-server or LLM problems; this
step is where those are found.

## Step 6: Report

One line first: mode, target (repo by absolute path), tools run. Then,
most severe first:

| # | Severity | Where | Finding | Abuse path | Fix |
|---|---|---|---|---|---|

- **Severity:** `Critical` (exploitable now from outside: remote code
  execution, data leaving the machine against the custody rules, auth
  bypass, secret in history), `High` (exploitable with a plausible
  foothold: a malicious web page, file, image or PR), `Medium`
  (defense-in-depth gap), `Low` (hygiene).
- **Where:** `path:line`; the scanner and rule ID if one found it.

Close with **Dismissed** (scanner hits dropped, counted per rule with
the reason), **Clean against** (checklist sections passed) and **Not
checked** (tools missing or offline, sections out of scope, and why).
