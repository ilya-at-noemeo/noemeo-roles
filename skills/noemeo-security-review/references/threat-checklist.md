# Threat checklist

Generic to all Noemeo repos. The repo's `CLAUDE.md` and decisions
narrow it: what counts as user data, where it may go, which servers
are local-only.

## Data custody

- User content (files, images, conversation, model state, local
  databases) goes only where the decisions allow. Check every path
  out: model calls, logs, telemetry, crash and error reports, URLs and
  query strings, analytics.
- A cloud call carries only what that one call needs, and the server
  side doesn't persist it unless a decision says so.
- Logs and error messages never include user content, tokens or
  personal data beyond an identifier.
- Personal data stored server-side has a stated purpose and a way to
  delete it.

## Local servers

- Binds to `127.0.0.1`, never `0.0.0.0` or all interfaces.
- Checks the `Host` header against an allowlist (DNS rebinding).
- State-changing requests check `Origin` or carry a per-launch token
  (CSRF from any page the user has open); no permissive CORS.
- File-serving and file-taking routes resolve paths and refuse
  traversal and symlinks out of the allowed directory.
- No debug mode, auto-reload or stack traces in shipped builds.

## Untrusted input reaching dangerous calls

Untrusted: anything from a request, a file the user opened, image
metadata, filenames, a host application, model output, a fetched page.

- Subprocess: argument lists, never `shell=True` with interpolation.
- SQL: parameters, never string formatting.
- Paths: no joins with untrusted names without resolving and checking
  the result; archive extraction checks member paths (zip slip).
- Deserialization: no `pickle`, `yaml.load`, `torch.load` without
  `weights_only`, `eval`, or `exec` on untrusted data; XML through
  `defusedxml`.
- Outbound requests to untrusted URLs (SSRF).
- HTML: user and model text rendered as text, never via `innerHTML` or
  unescaped templates.

## LLM calls

- Untrusted content in a prompt is delimited and declared as data,
  not instructions.
- Model output is untrusted: validated against its schema, never
  executed, never used as a path, URL, command or SQL without checks.
- A tool or action with side effects isn't triggered by model output
  alone where injected text could steer it.
- No secrets or other users' data in prompts.
- An endpoint that spends money on model calls has authentication and
  a limit per user (abuse here is cost).

## Secrets and credentials

- None in code, tests, fixtures, logs, history or built artifacts.
- Stored in the OS keychain or a secret manager; tests never touch the
  real keychain.
- Tokens are scoped and expire; refresh and revocation exist.

## Cloud endpoints and webhooks

- Every route authenticates; authorization checks the resource
  belongs to the caller (no ID guessing).
- Webhooks verify the signature over the raw body, reject stale
  timestamps and are idempotent per event ID.
- Input size limits; errors don't leak internals.

## Supply chain

- Lockfile committed; a new dependency is justified (maintained, the
  real package and not a typosquat, no install-time scripts needed).
- GitHub Actions pinned to a commit SHA; `permissions:` minimal per
  job; no `pull_request_target` that checks out PR code; no
  `${{ github.event.* }}` interpolated into `run:`.

## Distribution

- Signed and notarized; hardened runtime; only the entitlements the
  app uses.
- Updates fetched over HTTPS and their signature checked.
- No secrets in the bundle (`strings` on the binary and resources).
