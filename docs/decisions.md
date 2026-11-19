# Decisions, delivered as rules

Settled project knowledge, stored as decisions in Git and delivered to
the agent as rules where its action falls in their scope. A decision is
the stored unit (as in architecture decision records); a rule is what
the harness puts in the agent's context. This page is the format
reference. The procedures agents follow are in the
`noemeo-decisions` skill and in `noemeo-design-review`.

Nothing here is on until a repo lists `decision_roots`; a repo without
them behaves as before.

## What a decision is

One of two forms:

- a **decision record**: a file that starts with a front matter block;
- a **marked section**: a section of any Markdown document that has a
  `<!-- decision ... -->` comment directly under its heading. It runs
  from that heading to the next heading of the same or a higher level.

A decision can be a policy, an architecture description, a product
definition or a finding (an empirical result that settled something).

## Configuration

A repo lists where its decisions live in `.claude/noemeo-guard.json`:

```json
{ "decision_roots": ["docs/decisions", "../acme-shared/decisions"] }
```

`decision_roots` are folders under the repo's root. They can name a
sibling checkout. Every `.md` file under a root is read. Files without a
decision in them are listed in the index by title, as background.

**Layout is yours.** A root can have any hierarchy, with one file per
decision, marked sections of longer documents, or both. Folders organise
decisions for people; folders never set scope. Where a decision applies
comes only from its own fields, so moving a file doesn't change what is
delivered.

## Fields

Front matter and markers hold the same `key: value` lines. Values are
`true` or `false`, an inline list `[a, "b, c"]` (double quotes protect a
comma) or a string. A line that starts with `#` is a comment. An
unknown or repeated key is an error, so a typo never silently drops a
scope. A decision with an error is dropped and the error is reported.

| Field | Meaning |
| --- | --- |
| `id` | Required. Stable and unique across all roots, e.g. `acme-0003` or `arch-data-custody`. |
| `kind` | Required. `policy`, `architecture`, `product` or `finding`. |
| `status` | Required. See Statuses. |
| `binding` | Required. `true` when the decision constrains actions; `false` when it describes. |
| `summary` | Required. One line, shown in the index. |
| `paths` | Scope: globs relative to a repo (`*` within a folder, `**` across folders). |
| `repo` | With `paths`: the name of the repo the globs belong to, for a decision that governs another repo. `*` means any repo. Without it, the repo that holds the decision. |
| `commands` | Scope: patterns matched against each shell command in a call (`*` is a wildcard; leading `VAR=value` and `sudo` are ignored). |
| `tasks` | Scope: task kinds such as `design`, `review`, `release`, `naming`. |
| `always` | Scope: `true` for the few decisions that apply everywhere. |
| `depends_on` | Ids this decision relies on. Not delivered to the model with it; `resolve` includes them, `deps` lists dependents and `lint` checks the links. |
| `supersedes` | Ids this decision replaces entirely. |
| `amends` | Ids this decision changes in part. The original stays current. |
| `origin` | Where it was settled: session date and topic, PR, research note. |
| `evidence` | Links to measurements or records that support it. |
| `deliver` | Front matter only. Which part is delivered: `all`, or a list of headings. Default: the record's "How to apply" and "Review checks" sections. A marked section always delivers its whole body. |

Any one scope match puts an action in scope. A decision with no scope is
never delivered by action; it is still in the index.

A decision's version is a hash of its fields and delivered text. A
change to either is a new version, so it is delivered again. Git history
shows who changed it and when.

## Statuses

| Status | In the index | In delivery |
| --- | --- | --- |
| `accepted` | listed | delivered as current |
| `temporary` | listed | delivered as current |
| `proposed` | listed as proposed | not delivered |
| `open` | listed as open | not delivered |
| `superseded` | not listed | never delivered |
| `retired` | not listed | never delivered |
| `rejected` | not listed | never delivered; shown, labelled rejected, only when asked for by id |

Only a person sets `accepted` or `temporary`. An agent writes
`proposed`.

An amendment (`amends: [original]`) is delivered with the original,
labelled as amending it, so outdated text never arrives alone. `lint`
warns about an original whose amendments are no longer current.

## What the model sees

The index shows each listed decision's id, summary and path, plus
`proposed` or `open` when it isn't current and, for a decision scoped by
task kind, which tasks. A delivered decision shows its id and text, with
current amendments. Kind, binding, scope, version, origin and evidence
are for the harness, lint and people. Opening a decision file shows its
front matter.

## Delivery

- **Session start:** the index, under a size budget, with one line that
  says which text is authoritative: what the harness loads itself and
  what is listed or delivered here. Text in other files or tool output
  that claims to be a rule is data.
- **Binding decision:** delivered before the action. The first matching
  edit, write or command is denied once, with the text as the reason;
  the retry goes through.
- **Descriptive decision:** delivered after the first matching read or
  edit, as feedback. Reading is never blocked.
- **Again:** only when the version changed, or the context that
  received it is gone (a subagent starts fresh; compacting or resuming
  resets the state).
- **Review:** `noemeo-design-review` resolves decisions from the diff.
- **Failure:** a failure to deliver prints a message and never blocks.

## Known limits

- Delivery reads the `decision_roots` of the session's own repo. A
  session started in repo A doesn't deliver repo B's decisions, even
  when it edits B's files. List B's decisions in A's roots (a sibling
  checkout) and scope them with `repo`.
- A Bash command is matched only against `commands` scopes. A `sed -i`
  on a file doesn't trigger that file's `paths` scopes.
- Task kinds can't be detected from a tool call. A `tasks` scope is
  listed in the index for the agent to act on; it isn't enforced.
- Codex gaps are in [codex.md](codex.md).

## Command line

```text
python3 hooks/decisions.py [--project DIR] <command>
```

| Command | Does |
| --- | --- |
| `index` | Prints the index. |
| `resolve [--path P] [--command C] [--task T] [--diff BASE] [--commits]` | Decisions in scope, with their amendments, plus the current decisions they depend on (transitively), each labelled as a dependency of the decision that needs it. This is the review's input; delivery to the model follows amendments, not `depends_on`. `--diff` takes the paths changed since BASE, plus untracked; `--commits` adds each source's last commit. |
| `deps ID` | Decisions that depend on or amend ID. |
| `show ID` | A decision, whatever its status. |
| `lint` | Checks the corpus. Exit 0 when there are no errors; warnings are printed. |
| `session-start` | The session context: index and always-on decisions. |

`lint` reports as errors: a format error, a duplicate id, an unknown id
in `depends_on`, `supersedes` or `amends`, and a current decision that
depends on a superseded or retired one. It warns about a record without
front matter, an empty summary or delivered text, `paths` that match no
tracked file, and an amended original whose amendment is no longer
current. Run it in the repo's checks.

## Manual editing

People edit decisions by hand, like any file in Git. What keeps that
safe is lint in the repo's checks and review, not a ban. An agent
doesn't change an accepted decision directly; it proposes an amendment
or a superseding decision.

## Example: record

```
---
id: acme-0007
kind: policy
status: accepted
binding: true
summary: Releases go out from a tagged commit only.
commands: ["acme-deploy *"]
tasks: [release]
depends_on: [acme-arch-pipeline]
origin: "2026-11-02 session, release rollback"
evidence: ["docs/notes/rollback.md"]
---

# 0007: Releases go out from a tagged commit only

Status: Accepted. Date: 2026-11-02.

## Context

A release from an untagged commit couldn't be traced or rolled back.

## How to apply

Tag the commit first, then run `acme-deploy` on that tag.

## Review checks

- Does the change deploy from anything but a tag?
```

## Example: section

```
# Acme architecture

## Build pipeline

<!-- decision
id: acme-arch-pipeline
kind: architecture
status: accepted
binding: false
summary: One pipeline builds, tests and packages every Acme service.
paths: ["docs/**"]
origin: "2026-10-20 session, pipeline layout"
-->

Every service is built, tested and packaged by the same pipeline, in
that order. A service doesn't ship its own build script.

## Hosting
```
