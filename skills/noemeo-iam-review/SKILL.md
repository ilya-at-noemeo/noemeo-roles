---
name: noemeo-iam-review
description: Security review of AWS IAM and CI deploy access in Noemeo repos -- Terraform trust and permission policies, GitHub OIDC subjects, Lambda execution roles, state access, and the GitHub workflows and secrets that assume those roles -- checking least privilege, environment separation, privilege-escalation paths and Noemeo's environment/promotion decisions. Use when asked for an IAM or access security review, when a change touches aws_iam_* resources, policy documents, assume-role or OIDC trust, deploy roles or their workflows (noemeo-iam or any infra repo), or before applying an access change.
---

# Noemeo IAM review

Finds ways a role, policy or workflow grants more than intended. Static
by default; reads Terraform and workflow YAML, never applies anything.
Complements `/security-review` (general code security) and
`noemeo-design-review` (all decisions); this one goes deep on access.

## Step 1: Scope

Use the target named in the request. Otherwise: uncommitted changes,
else the branch against its base (`dev` in infra/IAM repos). Collect
every file that defines or uses access:

- `aws_iam_*` resources, `data "aws_iam_policy_document"`, inline
  `jsonencode` policies, `assume_role_policy`;
- Lambda/ECS execution roles and their policies in infra repos;
- `.github/workflows/*.yml` that use `aws-actions/configure-aws-credentials`
  (triggers, `environment:`, `if:` guards, which secret);
- tfvars that feed policy variables (state prefixes, environment
  names, repo names, apply environments).

Changes in one repo often depend on another (a role in noemeo-iam, the
workflow assuming it in an infra repo). If a sibling repo is checked
out next to the target, read the other half; otherwise list it under
"not checked".

## Step 2: Load the rules

Read the generic decisions in `../noemeo-foundation/decisions/` from
the current repo's root (a sibling checkout of the private
`noemeo-foundation` repo) -- at least 0006 (repo ownership, one CI role
per repo) and 0007 (environments, promotion, OIDC); if it isn't there,
say so rather than citing decisions from memory. Then the target
repo's `CLAUDE.md` (noemeo-iam's has the gated-stack checklist).

## Step 3: Check

Work through [`references/iam-checklist.md`](references/iam-checklist.md)
for every policy and trust document in scope. Resolve variables and
locals to their values per environment (read both `dev` and `prod`
tfvars) before judging a pattern -- `"${prefix}*"` is only as tight as
`prefix`. For each finding, write down the concrete abuse: who can do
what to which resource, starting from which foothold (a PR, a
dispatch from a feature branch, a compromised Lambda).

## Step 4 (optional): Validate with AWS

Only if the user explicitly agrees -- it uses their AWS credentials,
although these calls are read-only and free:

- `aws accessanalyzer validate-policy --policy-type IDENTITY_POLICY
  --policy-document file://<rendered.json>` (or `RESOURCE_POLICY` for
  trust policies) on each rendered policy;
- `aws iam simulate-principal-policy` for a specific "can role X do Y
  on Z" question raised in step 3.

Render policies from a real `terraform plan -out` + `terraform show
-json` when credentials allow, never by applying.

## Step 5: Report

One line first: target, repos covered, environments resolved. Then,
most severe first:

| # | Severity | Where | Finding | Abuse path | Fix |
|---|---|---|---|---|---|

- **Severity:** `Critical` (exploitable now: escalation to admin,
  cross-environment write, untrusted principal can assume), `High`
  (broader than intended, plausible abuse), `Medium` (defense-in-depth
  gap), `Low` (hygiene).
- **Where:** `path:line`, plus the resolved value when it matters.
- **Abuse path:** foothold -> action -> impact, one line.

Close with **Accepted by design** (broad grants that are intentional,
with the reason recorded in code or docs), **Clean against** (checklist
sections passed) and **Not checked** (and why). Report only; don't edit.
