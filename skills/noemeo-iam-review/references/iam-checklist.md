# IAM checklist

Generic to all Noemeo repos. Decision numbers refer to
`decisions/` in noemeo-foundation.

## Trust policies (who can assume)

- **No open principals.** No `Principal: "*"` / `AWS: "*"`; no other
  account's root without an `sts:ExternalId` condition.
- **Human roles require MFA** (`aws:MultiFactorAuthPresent = true`)
  and trust only the account root or named principals.
- **GitHub OIDC:**
  - `aud` is `StringEquals sts.amazonaws.com`.
  - `sub` patterns name one repo exactly (`repo:<org>/<repo>:...`);
    no wildcard in the org or repo segment, no bare `repo:<org>/*`.
  - Each infra repo has its own role, trusted only by that repo (0006).
  - **No deploy role trusts `:pull_request`, in any environment** --
    that subject has no target branch and a PR's plan runs the PR's
    code. PR plans use the read-only plan role (ReadOnlyAccess plus a
    deny guard) with `-lock=false` (0009).
  - **Environment subjects must include the branch** (0009):
    `repo:<org>/<repo>:environment:<name>:ref:refs/heads/<branch>`,
    which requires the repo's OIDC subject template to be customised
    (`repo`, `context`, `ref`). A branch-less environment subject is
    acceptable only behind an explicit, temporary transition flag.
    Jobs also guard on `github.ref` (0007), and environments carry
    deployment-branch rules as defense in depth. IAM deploy roles trust
    only their environment (no branch subject) (0009). GitHub plan
    limits (no enforced branch rules, branch protection or reviewers
    for private repos on Free) are why the branch check lives in AWS:
    don't flag their absence, do flag a branch-less subject.
  - Trust lists contain no subjects for environments or stacks that
    environment doesn't run (dead trust is still trust).
- **Account singletons** (OIDC provider, admin role, human users and
  groups) are created by one root only (dev); others look them up (0007).

## Permission policies (what they can do)

- **No full wildcards:** `Action: "*"`, `service:*`, or
  `Resource: "*"` on write actions. A `Resource: "*"` is acceptable only
  for actions with no resource-level support, scoped by a condition
  (e.g. `aws:RequestedRegion`) and commented as such.
- **Environment scoping (0007):** name-based ARNs end in the
  environment suffix (`...-${var.environment}`, `...-<env>-*` for
  derived names, `...:*` variants for log streams/qualifiers). Check the
  resolved prod values can't match dev resources and vice versa. List
  the services that can't be name-scoped (ID-based ARNs) as accepted,
  not silently.
- **State access:** each role reads/writes only its own environment's
  state prefixes; read-only on state it merely consumes
  (`terraform_remote_state`); `s3:ListBucket` limited by `s3:prefix`.
- **iam:PassRole** limited to specific role ARNs and conditioned on
  `iam:PassedToService`.
- **iam:AttachRolePolicy/DetachRolePolicy** conditioned on
  `iam:PolicyARN` (own environment's policies only).
- **Environment guard** (0009): every non-IAM role carries the policy
  denying actions on resources tagged with another environment.
- **Tag conditions in Deny statements** use `StringNotEquals` + `Null =
  false`; `StringNotEqualsIfExists` there would deny untagged resources
  and break workloads.
- **Taggable but not name-scopable services** (KMS, EC2, RDS, Secrets
  Manager, logs, Cognito, Bedrock guardrails, API Gateway): write
  grants conditioned on `aws:ResourceTag/Environment` (and
  `aws:RequestTag/Environment` on create).

## Privilege escalation

Flag any role that can, directly or in combination:

- modify its own or a more privileged role/policy
  (`iam:PutRolePolicy`, `AttachRolePolicy`, `CreatePolicyVersion`,
  `SetDefaultPolicyVersion`, `UpdateAssumeRolePolicy`) -- for the IAM
  deploy role this is inherent; confirm it's limited to its own
  environment's `Noemeo*-<env>` resources and manual-apply only;
- create a role or function and pass it a more privileged role
  (`iam:CreateRole`/`lambda:CreateFunction` + broad `iam:PassRole`);
- change code that runs with another role (`lambda:UpdateFunctionCode`
  on functions whose execution role is broader than the caller);
- create access keys or login profiles (`iam:CreateAccessKey`,
  `CreateLoginProfile`, `UpdateLoginProfile`);
- reach the other environment through any of the above.

## Workload roles (Lambda, ECS)

- Every CI-created workload role carries `NoemeoWorkloadBoundary-<env>`,
  and the deploy policy's create/put-policy actions require it via an
  `iam:PermissionsBoundary` condition (0009).

- Each function has its own role; policies name the exact tables,
  log groups, secrets and model/inference-profile ARNs it uses.
- Model invocation (`bedrock:InvokeModel*`) scoped to the intended
  model or inference-profile ARNs, not `*`.
- No `iam:*`, no wildcard data access, no permission to disable
  logging or guardrails.

## Secrets and credentials

- No `aws_iam_access_key`, no static keys in code, tfvars, workflow env
  or Terraform outputs.
- One GitHub secret per role per environment
  (`AWS_*_ROLE_ARN_DEV` / `_PROD`); no secret shared across
  environments (0007).

## Workflows that assume roles

- `permissions:` grants `id-token: write` only to jobs that need AWS;
  everything else read-only.
- Never `pull_request_target` (or `workflow_run` on untrusted code)
  combined with AWS credentials.
- Prod workflows: no `pull_request` trigger; plan on push to `prod`,
  apply only via `workflow_dispatch` with the ref guard and the
  protected environment (0007).
- Third-party actions pinned to a version (ideally a commit SHA).
