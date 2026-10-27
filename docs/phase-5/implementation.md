# Phase 5: characterization and schema/data review

The PDF's page 6 defines the Characterizer and Schema/Data responsibilities and joint G2 review. Its page 5/6 G3-before-G2 ordering conflicts with the page 11 supervisor diagram. The explicit Phase 5 request and existing canonical lifecycle take precedence: G1 → characterization/schema → G2 → planning → G3. Phase 4 analysis/module inventory feeds coverage. Conversion remains gated by G1/G2/G3.

## Delivered behavior

All eight proposed Phase 5 endpoints are registered. They use job membership checks; capture and disposable validation require `job:intake`, freeze review requires `gate:approve_g2`, reads require `job:read`. Test-case detail checks the owning job to prevent IDOR.

Capture requests require an idempotency key and may supply approved scenarios, replay notes, source tables and target tables. Scenario inputs are passed to the configured legacy adapter; callers cannot supply actual observations, commands, connection URLs or host mounts. Capture executes each scenario twice and checks output and side-effect reproducibility. Explicit expected values act as assertions; otherwise the observed output becomes the golden baseline. Existing test files are discovered from Phase 4 inventory, but discovery does not claim execution of those tests. The adapter should run the relevant existing test/scenario in its image.

Normalization uses exact JSON pointers, a justification and typed timestamp/UUID checks. Array ordering is preserved unless `contract_allows` is explicit. Side effects are compared without normalization. Missing fields, invalid rules and meaningful differences cannot silently become passes. Coverage includes inventory modules/interfaces, scenario behaviors, untested paths and limitations; it is not branch or line coverage.

The existing Artifact, TestCase, TestResult, AgentRun, WorkflowGate and AuditEvent tables store Phase 5 evidence. No database schema changes or migration are needed. JSON artifact bytes are canonical and SHA-256 checked on reads. New captures publish new versions, retain historical bytes and frozen test definitions, invalidate current/dependent G2/G3/G4 approvals and test results, and checkpoint the return to characterization. Idempotent retries return the original capture. Capture records zero model tokens/cost because these steps are deterministic.

G2 freeze requests delegate review preparation to SupervisorService; only the existing human gate decision API grants approval. SupervisorService also owns baseline revision checkpoints/invalidation and planning eligibility. Approval checks current suite and schema artifact hashes, rejects failing, non-reproducible or required unavailable baselines, and marks the corresponding test cases frozen. Schemas with tables additionally require the latest hash-bound disposable validation to pass with sample data. Rejections return to characterization for a new capture/version. Compatibility gate URLs route G2 through the same policy. Stale approval idempotency keys cannot authorize a revised baseline.

## Legacy runtime setup

Set `PHASE5_LEGACY_IMAGE` to an already provisioned image (prefer a digest), and `PHASE5_LEGACY_COMMAND_JSON` to the image's adapter argv, for example `["python", "/adapter.py"]`. The adapter reads one JSON object from stdin: `{"scenario":"name","inputs":{}}`; it must write exactly `{"output":...,"side_effects":...}` to stdout. The adapter bundles required legacy tests and dependencies. Environment notes are recorded, never injected as process variables. Do not place credentials in fixtures.

Docker execution denies network and host mounts, uses a read-only filesystem and unprivileged user, drops capabilities, limits CPU/memory/PIDs/output/time, and never pulls images. The image must work under these restrictions. CPU/memory settings are currently fixed at 1 CPU / 256 MiB. The adapter must encode relevant side effects in its response. Persistent external-service behavior requires a future reviewed sandbox adapter; it is not inferred or simulated.

If Docker or the configured adapter is unavailable, cases remain UNAVAILABLE and coverage reflects the missing evidence. An entirely unobserved baseline cannot be approved. This workstation's Docker daemon was unavailable during implementation; real legacy sandbox execution remains an environment acceptance check.

The adapter response accepts exactly `output` and `side_effects`; duplicate JSON keys, nonfinite JSON numbers, extra fields and malformed evidence are rejected. The 30-second deadline includes stdin backpressure, stdout/stderr reads and process completion. Failure reports distinguish missing configuration, missing Docker executable, unreachable daemon, absent local image, adapter exit, timeout and invalid evidence. Non-reproducible observations use `NON_REPRODUCIBLE` (persisted TestResult classification `NONDETERMINISTIC`); the older `PASSED`/`FAILED` case values remain compatible. Coverage adds observed/unobserved and PASS/FAIL/UNTESTED labels, while discovered test files remain DISCOVERED/UNTESTED.

`test_real_legacy_environment_acceptance` is an opt-in real adapter acceptance path. Configure an approved representative scenario in `PHASE5_ACCEPTANCE_SCENARIO_JSON` (a Scenario JSON object) together with the image and command. No image is pulled or sandbox policy weakened by the test. Missing configuration is a skip marked PENDING ENVIRONMENT, never a fabricated success.

## Schema and disposable validation

Ordinary bounded CREATE TABLE definitions can be inventoried from staged SQL files into an isolated in-memory SQLite database. Paths are restricted to the job workspace. Other SQL statements are never executed; unsupported dialect constructs, defaults, CHECK expressions, triggers and composite constraints are reported for manual review. ORM/schema evidence from Phase 4 is displayed. Explicit structured source/target schemas override the discovered subset after review.

Proposals include keys, nullability, uniqueness, relationships, length checks, type changes/removals, identity mapping rules, DDL, count/integrity queries and rollback notes. Validation supports SQLite INTEGER/REAL/TEXT and schema-only BLOB declarations; BLOB sample conversion, dialect-specific semantics, composite keys and nonidentity transformations require further reviewed adapters. No implicit casts, truncation or production-database connections are accepted. Samples are inserted with parameters into `:memory:`, constraints and counts are checked, and rollback/drop is verified. Empty samples validate DDL only and cannot satisfy the G2 data-validation prerequisite. Source data is never changed.

Unsupported discovered semantics and composite keys produce `REVIEW_REQUIRED` and block G2 approval until reviewed schema overrides resolve the assumptions. Empty samples return DDL-only validation status. Oversized SQLite integers, nonfinite REAL values and numeric implicit conversions are rejected before insert. The review UI shows persisted validation status and explicit manual-review/unobserved warnings.

## Review UI

Open `#/characterization` or the Characterization & Schema sidebar item. Select a job, inspect discovery gaps, submit scenario/schema JSON, filter cases and compare expected/actual values, inspect coverage/bugs/normalization/environment/hash, validate disposable samples, request G2 review and record approval/rejection with a rationale. Reviewers must resolve the displayed schema assumptions and coverage limitations before approval.

## Verification

`backend/tests/test_phase5.py` uses isolated in-memory databases and a controlled legacy adapter double. It covers golden changes, normalization bounds, side effects, missing runtime, coverage gaps, idempotency, source DDL discovery, parameterized upgrade/rollback, null/duplicate/truncation/type/FK errors, reconciliation, integrity tampering, G2 freeze/reject/revise, invalidation, all new endpoints and read/write authorization. The frontend suite includes Phase 5 review rendering and API contract checks. Real Docker execution is not claimed by the adapter-double tests.
