# Engineering principles

The design principles behind `noemeo-roles`. Some are enforced today,
some are only required by roles and skills, and some are goals. Each
one says which; the [README](../README.md#what-it-does-today) lists the
mechanisms themselves.

1. **Human ownership and accountability.** Humans own product intent,
   engineering standards, consequential trade-offs, and final
   accountability. Delegating a task does not delegate responsibility
   for its acceptance.
   *Status: required by roles (the owner decides; agents propose).*
2. **Separation of concerns.** Product, architecture, implementation,
   testing, review and research have distinct scopes, authorities and
   handoffs. The author does not approve their own change; the test
   engineer does not repair production code to make tests pass; the
   reviewer reports findings rather than silently changing what they
   review.
   *Status: partly enforced. The review gate requires a separate
   reviewer's approval, and the reviewer agent has no file-editing
   tools. The test engineer needs them to write tests, and tool
   permissions can't limit them to test files, so its
   no-product-code limit rests on its role.*
3. **Process independence from machinery.** Roles, acceptance criteria
   and governance rules are defined outside Claude Code, Codex, or any
   model's private context. Provider adapters implement the contract
   and expose their differences; interchangeability is a goal to
   verify, not assume.
   *Status: implemented for roles, skills and core hooks, which both
   tools read from one source; the Codex installer's `--check` catches
   stale copies. Equivalent behaviour across tools is not measured.*
4. **An explicit development lifecycle.** Requirements, design,
   implementation, independent testing, review and delivery are
   connected by declared inputs, outputs, exit criteria and revision
   loops -- not an open-ended conversation.
   *Status: partly. `noemeo-ship` fixes the order from request to PR;
   per-stage inputs, outputs and exit criteria are not yet declared.*
5. **Independent verification.** A change passing the author's own
   checks is not the end of verification. A separate test engineer
   designs tests and demonstrates that they can fail; a separate
   reviewer challenges the proposed change, the tests included.
   *Status: the review step is enforced by the review gate; proving
   tests can fail is required by the testing role, not checked.*
6. **Executable governance.** Safety- and quality-critical constraints
   belong in mechanisms such as hooks and CI checks wherever
   practicable, not solely in instructions that models may fail to
   follow. Enforcement must be checked for activation, bypasses and
   failure modes.
   *Status: partly. The hooks have tests, including attempts to slip a
   PR past the review gate; no CI-side equivalent exists, so the checks
   depend on hooks being installed and active.*
7. **Auditability and traceability.** Requirements, decisions, code
   versions, tests, failures, review findings, approvals and policy
   decisions should form inspectable evidence of what happened and
   which rules were applied. Observability is not the same as an
   independently verifiable audit trail.
   *Status: goal. Review verdicts are recorded against a fingerprint of
   the reviewed change; the agent usage log covers Claude Code only.*
8. **Evidence over assertion.** Tests should show that they detect the
   failures they claim to guard against. Model and prompt changes
   should be measured against baselines rather than judged by
   persuasive explanations.
   *Status: required by roles and skills, not checked.*
9. **Controlled, proportional autonomy.** Agents act within permissions
   and role boundaries. The degree of review and enforcement should
   reflect the scope and risk of the change, without eliminating
   mandatory safeguards.
   *Status: goal. Permissions and role boundaries apply, but every
   change gets the same pre-PR review whatever its size or risk, and
   the PR itself is reviewed by a person, outside this machinery.*
10. **Reproducibility and continuous improvement.** Versioned artifacts,
    configurations and recorded results should support repeatable
    checks. The process should evolve in response to observed defects,
    review results and execution cost rather than assumptions about
    model capability.
    *Status: goal.*

## Engineering process

The lifecycle is iterative, not waterfall:

```text
Human-owned intent, requirements and acceptance criteria
                         |
                    Architecture
                         |
                  Implementation <------------------+
                         |                          |
            Independent test engineering            |
             (write tests; prove they fail)         |
                         |                          |
            Run tests and assess failures ----------+ failures
                         |                          |
             Candidate change + evidence            |
                         |                          |
                Independent review -----------------+ findings (code or tests)
                         |
                       Ready
                         |
                 PR / delivery gate
```

A passing test run is necessary where tests apply, but never sufficient
proof that a change meets its requirements. The reviewer can challenge
the tests themselves, including missing cases and mistaken assertions.
Findings go back through implementation and testing, and any edit voids
an earlier approval. The workflow implemented today is the
[`noemeo-ship` skill](../skills/noemeo-ship/SKILL.md).

## What an auditable change should establish

A useful review record connects **requirement -> design decision ->
change -> test and result -> review finding -> disposition ->
approval**. It identifies which exact revision was checked, the role and
tool responsible for each step, any exceptions or failed controls, and
the final decision. Re-running the automated checks should not depend
on private chat history.

This is the target, not the current state: today the repository
enforces selected controls and preserves handoff context, but does not
provide complete, cross-provider auditability.
