# The `noemeo` plugin: install, update, agents

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

Skills use the open `SKILL.md` format (name + description frontmatter,
plain Markdown body), readable by people and by other agent tools.
**Agents only when a separate context is the point** -- a reviewer that
must not share the author's reasoning, or a self-contained piece of a
role's work worth delegating. Each is a thin adapter for a role
definition in `roles/` (`noemeo-code-reviewer` fills `roles/engineering/testing.md`,
`noemeo-ai-engineer` fills `roles/engineering/ai-engineering.md`,
`noemeo-backend-architect` fills `roles/engineering/architecture.md`,
`noemeo-researcher` fills `roles/research/research.md`,
`noemeo-ux-designer` fills `roles/product/ux-design.md`,
`noemeo-product-manager` fills `roles/product/product-management.md`): it
loads the role and the skills rather than restating them.
`noemeo-test-engineer` fills the same testing role as
`noemeo-code-reviewer`, from the
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
