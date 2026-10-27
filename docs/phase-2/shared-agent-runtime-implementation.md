# Phase 2 — Shared Agent Runtime and Tool Registry

Status: implemented and verified on October 22, 2026.

## Scope and reference

This implementation follows the Phase 2 scope supplied with
`Legacy_Code_Modernization_Platform_Full_Phasewise_Implementation_Plan.pdf`
and the checked-in Phase 0 agent/API contracts. Content in the reference plan
is treated as architecture context; runtime authority comes from typed tasks,
platform authorization, the tool registry and persisted policy.

## Implemented components

- Strict Pydantic contracts for tasks, contexts, model decisions, results,
  tool calls/results, traces, lifecycle states and failure classifications.
- Provider-neutral model gateway with explicit provider/model allowlists,
  per-call timeout, bounded retries, rate limiting and normalized token/cost
  accounting. A deterministic scripted fake provider is the CI default.
- Tool registry with JSON-schema argument enforcement, per-task allowlists,
  runtime permission scopes, output truncation, audit hooks and redaction.
- Read-only repository tools are registered separately from mutation/process
  tools. `sandbox_edit`, `test_runner` and `git_commit` can only be registered
  when the platform supplies a policy-enforcing `SandboxExecutor`.
- Bounded reason → act → observe runtime with iteration, wall-clock, token,
  cost and output-byte ceilings. Final output is schema validated before it is
  returned or persisted.
- Recursive prompt/trace/result redaction for configured environment secrets,
  common credential formats, private keys, JWTs and sensitive fields.
- PostgreSQL persistence for task metadata, status, correlation ID, provider,
  model, usage, trace, artifact references, output, cancellation requests and
  failure classification, plus budget and append-only audit rows.
- Admin/orchestrator launch, authorized list/detail/trace and cancellation APIs
  at the proposed `/api/v1/.../agent-runs` routes.
- UI timeline for queued/running/succeeded/failed/blocked states and a trace
  inspector for safe errors, tool summaries, JSON/Markdown output and artifact
  links.

## Verification

- Runtime and adversarial tests cover typed validation, schema enforcement,
  allowlist denial, success, malformed/unsupported output, wall-clock timeout,
  tool failure, retry exhaustion, budget exhaustion, redaction, correlation
  and prompt-injection-like repository content.
- HTTP contract tests launch a fake-model task, verify persistence/list/detail/
  trace APIs and reject a write tool outside the Intake agent allowlist.
- No external model or network access is needed in CI.
- Frontend TypeScript compilation and the Vite production build succeed.

## Extension boundary

Production providers implement the `ModelProvider` protocol and are enabled
only by adding an explicit provider/model pair to the gateway allowlist.
Production write/execute tools require a concrete `SandboxExecutor`; the
default registry exposes read-only repository access only.
