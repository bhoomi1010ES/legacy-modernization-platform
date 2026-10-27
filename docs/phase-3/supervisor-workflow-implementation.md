# Phase 3 — Durable supervisor workflow

Phase 3 implements the outer modernization loop described by the phase plan and the checked-in Phase 0/TDD workflow rules. The attached planning document was treated as design context; executable behavior is defined by the user request, typed schemas, state machine, and tests.

## Runtime design

- `StateGraph[SupervisorState]` contains explicit intake, analysis, G1, characterization, G2, planning, G3, conversion, verification, integration, G4, pause, completion, failure, and cancellation nodes.
- Only one graph node runs per database transition. `WorkflowCheckpoint` is written before and after the node (or as an interrupt), preventing an in-memory traversal from crossing a durable boundary.
- The PostgreSQL checkpoint sequence is allocated under a locked `Job` row. Restart recovery records reconciliation without replaying the node or an irreversible side effect.
- Side effects use a unique idempotency key in `workflow_outbox`; bounded retries end in `DEAD_LETTER`.
- Entering G1–G4 automatically creates a versioned `WorkflowGate` bound to the latest artifact IDs and SHA hashes. The interrupt releases module worker leases.

## Gate invariants

- G1–G4 decisions require an authenticated human with job membership and the matching approval permission.
- Decisions are append-only and store reviewer, timestamp, rationale, options, waivers, and the exact artifact hash map reviewed.
- A stale artifact hash returns `409 Conflict`.
- Row locks serialize competing reviewers. A repeated idempotency key returns the first result; a different second decision is rejected.
- Rejection or needs-changes routes to the defined revision node. A revised bound artifact invalidates that approval, all dependent approvals, and affected test results.
- CodeWriter leasing is impossible until current G1, G2, and G3 instances are all approved.

## Scheduling and controls

- Ready modules are leased in dependency order with PostgreSQL `FOR UPDATE SKIP LOCKED`.
- Expired leases are reconciled to pending work after restart.
- Effective capacity is the minimum of job, provider, and sandbox concurrency limits.
- Job and module budget ceilings are checked before work is leased. Exhaustion pauses/escalates instead of starting another task; the workflow API reports an 80% warning.

## API surface

- `GET /api/v1/jobs/{job_id}/workflow`
- `GET /api/v1/jobs/{job_id}/gates`
- `GET /api/v1/gates/{gate_id}`
- `POST /api/v1/gates/{gate_id}/decision`
- `POST /api/v1/jobs/{job_id}/resume`
- `POST /api/v1/jobs/{job_id}/cancel`
- `GET /api/v1/jobs/{job_id}/events`

The legacy nested gate-decision endpoint remains for client compatibility. New clients should use the versioned gate endpoint so artifact hashes and idempotency are mandatory.

## Verification

- Backend: full suite `138 passed, 1 skipped`; the focused Phase 3 suite passes `11` tests.
- Frontend: `13 passed`; TypeScript and Vite production build succeeded.
- Database: migration `b3d4e5f60718` applied and is the current Alembic head.

The locked repository-local `.pytest_temp`/`.pytest_cache` directories are pre-existing Windows filesystem artifacts. Test verification uses a fresh temporary base directory to avoid those unrelated locks.
