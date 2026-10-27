# Phase 5 acceptance gap audit

Audit before edits, 2026-10-23. Canonical lifecycle: G1 → Characterization → Schema/Data → G2 human review → Planning → G3 → Conversion → Verification → Integration → G4.

| Requirement | Existing implementation | Missing | Action |
|---|---|---|---|
| Phase 4 discovery | Module/interface and test-file inventory consumed; discovery never marks tests executed | Explicit observed/discovered status fields | Extend report labels without changing stored historical bytes |
| Adapter sandbox | Network-none, no mounts/pulls, unprivileged, read-only, resource/output bounds | Exact output contract, full timeout including stdin, safe precise failure reasons | Tighten existing replay function; test real environment when available |
| Reproducibility | Two output/side-effect observations compared | Distinct NON_REPRODUCIBLE outcome and structured evidence | Extend typed evidence and existing result classification |
| Normalization | Exact paths and justification, typed timestamps/UUIDs, opt-in ordering | Invalid JSON-pointer escapes, negative array indexes, whitespace-only rationale | Tighten existing validation |
| Artifacts/idempotency | Canonical bytes/hash, retained versions, job lock, request keys | Request identity currently hashes redacted inputs; stale approval replay | Preserve exact request identity and reject unsafe input; check replay freshness |
| Supervisor authority | Gate opening delegates to Supervisor; GateService decides humans | Capture directly writes job status/checkpoints/invalidations | Move revision orchestration into existing SupervisorService |
| Schema/data | Existing DDL discovery, mapping/diff, in-memory validation and rollback | REVIEW_REQUIRED status for unsupported semantics; durable validation status in UI | Extend existing plan/report and gate prerequisites |
| G2 governance | Current hashes, observed case, schema sample validation checked | Pending/rejected/approved → Planning proof; stale approvals on planning entry | Guard existing Supervisor/router/orchestrator entry; add canonical E2E tests |
| Eight APIs/auth | Existing membership/RBAC and IDOR checks | Comprehensive unauthenticated/read/write coverage and audit assertions | Extend existing Phase 5 tests |
| UI | Job/test filters, previews, coverage, hash, schema/plan, G2 decisions | Explicit unobserved/manual-review/data-validation warnings | Extend existing review component/tests |
| Environment | .env DEBUG values already valid; inherited process DEBUG=release | Invalid inherited process configuration; real sandbox acceptance | Set valid process DEBUG for verification; report daemon/config availability explicitly |
| Regression/quality | 21 Phase 5 and 28 frontend tests from implementation | Full current backend run; type/lint/security evidence | Run complete suites; distinguish pre-existing failures and environment limitations |

No new services, tables, routes, hashing engine or gate engine are needed. Full baseline regression started before implementation edits. Real legacy acceptance is pending environment unless a daemon and configured image/adapter become available.
