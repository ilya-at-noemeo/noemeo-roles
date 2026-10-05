---
name: noemeo-test-engineering
description: Designs and builds the automated tests that keep a Noemeo repo's behaviour verified -- picking the right level per behaviour (unit, integration through the real seam, browser end-to-end with a mocked network, fakes for a host application's SDK, a manual checklist for the rest), keeping tests hermetic and free of paid calls, proving each test can fail, and wiring them into the repo's normal check command. Use when adding or extending a test suite, when a surface (a web UI, a plugin, a script) has no automated tests, when turning one-off verification into repeatable tests, or when asked for a test strategy.
---

# Noemeo test engineering

Procedure for the building side of the testing role
(`../../engineering/testing.md` relative to this skill's base
directory). Reviewing a change is the other side -- that's
`noemeo-code-reviewer`. Read the repo's `CLAUDE.md`, `docs/decisions/`
and how it runs its checks (README, `pyproject.toml`, `package.json`,
CI workflows) first; they override anything generic here.

## Step 1: Intent and inventory

- **What must hold:** list the behaviours worth pinning, in the words of
  the product docs or the change's intent -- user-visible outcomes,
  rules the decision logs impose, and bugs already fixed once.
- **What exists:** each surface (server/library, web UI, plugin or
  script running inside another application, infra) and the tests that
  cover it today. A surface verified only by hand, or by a script that
  was run once and not kept, counts as untested.
- **Gaps first:** start where a regression would be most costly and
  least visible.

## Step 2: The lowest level that exercises the real behaviour

| Behaviour | Level |
| --- | --- |
| Pure logic, parsing, formatting | Unit test |
| A route, graph or workflow end to end | Integration through the real code, faking only the outermost seam |
| A user flow in a web UI (keyboard paths, error states, focus) | Browser test (e.g. Playwright) against the real page, network mocked per route |
| Code that runs inside a host application (an editor plugin, an extension) | Unit tests against a small fake of the host SDK, covering only the calls the code makes |
| Rendering, screen readers, real devices, the host application itself | A short manual checklist in the repo's `docs/` |

Fake at the seam the code already has. For model calls, that's the
client the driver passes to the agent (decision 0002). Never fake the
unit under test.

## Step 3: Rules for every test

- **No paid or live calls.** Model APIs, cloud resources and
  third-party services are mocked. If a test can't run without one, it
  doesn't belong in the default suite; say what would be needed.
- **Hermetic.** Temp directories and in-memory stores; never the
  developer's real data, logs or home directory. Before running a new
  test, check it goes through the repo's isolation fixtures (conftest
  or equivalent). Importing helpers from another test module can skip
  them.
- **Deterministic.** Wait for a condition, not a fixed sleep. Pin
  clocks, random seeds and ordering.
- **Specification-shaped.** Name each test for the behaviour it pins
  ("resending after a failed reply records the message once"). Use
  literal inputs and expected outputs. Assert what a user or caller
  observes, not private structure.
- **Regression tests reproduce first.** For a bug, write the test, see
  it fail on the unfixed code, then fix.
- **Accessibility in browser tests:** run an automated audit (e.g.
  axe-core) on each main screen, and drive keyboard-only paths. List
  what automation can't judge in the manual checklist.

## Step 4: Prove the tests can fail

For each behaviour, break it in one small way that matters: flip a
condition, drop a guard, change a threshold. Confirm at least one test
goes red, then restore the code. If nothing fails, the test doesn't
pin the behaviour: tighten it or add a case. Never leave product code
modified.

## Step 5: Wire it in

- The tests run from the repo's normal command (e.g. `pytest`), so the
  code reviewer and CI run them without extra steps. If a slow or
  heavy group needs to be opt-in, gate it behind a marker or flag and
  say so.
- New tooling goes in dev dependencies, with any install step (browser
  download, interpreter) in the README.
- Report the suite's run time; keep the default run fast.

## Step 6: Report

- What's covered now: behaviour → test, per surface.
- Proof of failure: which deliberate break turned which test red.
- Commands run and their result (counts, run time).
- What's still untested and why, plus the manual checklist.
- Defects found while writing tests: report them with a failing test
  (marked expected-to-fail if the fix isn't yours to make), and hand
  them to implementation.
