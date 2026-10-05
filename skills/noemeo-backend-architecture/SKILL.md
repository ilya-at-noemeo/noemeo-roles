---
name: noemeo-backend-architecture
description: Designs or reviews the backend of a Noemeo system -- where data lives and who owns it, component and service boundaries, API contracts (contract-first, matching the repo's existing style), consistency and failure modes, schemas, security at each boundary, observability and cost sized to real need -- grounded in Noemeo's decision logs rather than generic microservice defaults. Use when designing a new service, endpoint, API, Lambda, schema or storage, splitting or merging components, choosing a protocol or datastore, or when asked to review a backend design or architecture.
---

# Noemeo backend architecture

Procedure for the architecture role (`../../engineering/architecture.md`
relative to this skill's base directory) on backend work: services,
APIs, data and the boundaries between them. Model-backed components go
to `noemeo-llm-engineering` once this procedure has decided a model
belongs there; IAM and deploy access to `noemeo-iam-review`.

Adapted from the community `development-team/backend-architect`
template (claude-code-templates). Its defaults -- microservices,
Kafka, mTLS, Vault, Prometheus, "scale horizontally from day one" --
are options to justify here, not starting points.

## Step 1: Context

1. **Decisions:** read `../../decisions/` relative to this skill's base
   directory -- especially 0002 (driver/agent boundary), 0003 (build
   capacity, not usage), 0006 (infra repo ownership), 0007
   (environments) and 0008 (no VPC by default).
2. **The repo:** its `CLAUDE.md`, `docs/architecture.md`,
   `docs/decisions/` and `docs/schema.md` if present, in full. Products
   record there what may leave the user's machine and what the cloud is
   allowed to do; those rules outrank anything below.
3. **What exists:** how current services, handlers and contracts are
   built (framework, packaging, error shape, versioning, auth). A new
   design extends the existing pattern unless there's a stated reason
   not to.

## Step 2: The problem, before the shape

Write down, without naming any technology:

- **Job:** what the component does, for whom, and what "correct" means.
- **Data:** each piece of data it reads or writes, who owns it, where
  it must live (the user's machine, a shared cloud store, nowhere
  durable) and for how long. User content leaving the machine, or
  being kept longer than one call, is a custody decision for the
  product's decision owner -- surface it, don't make it.
- **Load and targets:** current and near-term volume, latency
  (P50/P95), availability, cost ceiling. Unknown is a valid answer;
  say so instead of inventing numbers.
- **Forcing cases (0003):** for each capability the design would add
  (a queue, a cache, a second service, a new datastore, a VPC), the
  concrete need that requires it now. No named case: leave room for it
  in the design and don't build it.

Ask only for what's genuinely unknown and changes the design.

## Step 3: Design

- **Boundaries:** draw lines around data ownership, not around nouns.
  One deployable until a real reason (independent scaling, a different
  owner, a separate trust boundary) justifies two. Drivers read
  config and pick transports; agents and core logic take plain
  parameters (0002). Generic repos define contracts without naming
  products (0004); infrastructure goes in the repo 0006 assigns.
- **Contract first:** write the interface before the implementation --
  request/response types (Pydantic, JSON Schema, or OpenAPI when there
  are external clients), status codes, the error shape, idempotency
  for anything retried, pagination, limits and timeouts. Version only
  when an incompatible change has a real consumer to protect.
- **Protocol:** plain HTTP+JSON unless a stated need says otherwise
  (streaming, a schema-heavy internal mesh). Pick on the use case and
  say why.
- **Consistency and failure:** per write, strong or eventual and why.
  For each external call: timeout, bounded retries with backoff, what
  happens on partial failure, and what the user sees. Prefer
  synchronous calls until async solves a named problem (long work,
  bursty load, decoupled owners); an async step needs a dead-letter
  path and an owner who looks at it.
- **Data:** schema with keys, indexes for the actual queries, and a
  migration path from what exists. Choose the datastore by access
  pattern, cost at expected load, and operational burden -- managed
  and serverless first. Sharding and read replicas only with a
  measured need.
- **Security at each boundary:** authentication where requests enter,
  authorization checked deterministically in code (never decided by a
  model or taken from model output), input validated against the
  contract, secrets from the platform's secret store or environment
  injected by the driver, never in source or logs. Least-privilege
  execution roles (hand IAM detail to `noemeo-iam-review`). Check the
  OWASP API Top 10 against the contract.
- **Observability, sized to need:** structured logs with a request ID
  carried across calls; per-endpoint rate, errors and duration from
  the platform's built-in metrics; alarms on what someone will act on.
  Never log user content or secrets. Add tracing or a metrics stack
  when there are enough hops to need it.
- **Cost:** estimate per user action and per month at expected load,
  with the inputs stated. Flag anything with a fixed monthly floor
  (NAT, always-on instances, provisioned capacity).
- **Names:** name every new concept precisely; a new mechanism gets a
  new name, not a reused one (0001).

Verify current provider behaviour, limits and prices in their docs
(web search) before designing around them, not from memory.

## Step 4: Check it

Run `noemeo-design-review` on the design. Then try to break it: the
most likely failure, the most expensive failure, what happens at 10x
load, and what has to be redone if the next likely requirement
arrives. Fix or record each.

## Step 5: Output

A design doc (in the repo's `docs/` when asked to write one, otherwise
in the reply) with:

1. **Problem** -- job, data and custody, targets, forcing cases (step 2).
2. **Design** -- a diagram (Mermaid or ASCII) of components and data
   flow, marking the user's machine / cloud boundary where there is one.
3. **Contracts** -- interface definitions with example requests,
   responses and errors.
4. **Data** -- schema, indexes, migration.
5. **Decisions and trade-offs** -- each choice with what was rejected
   and why; deferred capabilities with the forcing case that would
   bring them in.
6. **Failure modes, security, observability, cost** -- per step 3.
7. **Open questions** -- what the product owner must decide (custody,
   scope) and what's unmeasured.
8. **Hand-offs** -- what implementation builds first, what AI
   engineering owns, and what the testing role must verify for the
   design to count as correct. A settled, generic choice becomes a
   proposed entry in `decisions/`; a product-specific one goes in the
   product's `docs/decisions/`.

## Review mode

When reviewing an existing design or change instead: steps 1-2 to
establish intent and constraints, then report against step 3's
headings, most severe first, with `path:line` or doc section, the
condition that breaks it, and a suggested fix. Don't redesign beyond
what the findings need.
