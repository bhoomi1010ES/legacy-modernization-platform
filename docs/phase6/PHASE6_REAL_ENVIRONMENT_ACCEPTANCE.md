# Phase 6 real-environment acceptance — 23 October 2026

## Decision

**Real acceptance: FAIL.** Docker acceptance now runs successfully, but the complete exit chain is not accepted. The real model request was rejected with HTTP 402; the user explicitly chose to leave model acceptance pending. Actual Git integration/system testing was also found to be unimplemented behind a success-reporting placeholder. That placeholder now fails closed, rather than publishing false G4 evidence.

Phase 6's existing conversion/verification implementation is retained, with targeted evidence and safety fixes below. This is **not** a claim that the requested integrated acceptance is complete.

PHASE 6 IMPLEMENTATION COMPLETE

REAL ENVIRONMENT ACCEPTANCE REMAINS OPEN

## Environment and provenance

| Item | Observed value |
|---|---|
| Host | Windows 11 Pro, 10.0.26200, x64 |
| Backend Python | 3.12.10, existing `backend/.venv` |
| Docker client / engine | 29.6.2 / 29.6.2, API 1.55 |
| Desktop | 4.84.0 (234817), desktop-linux context, WSL2 Linux/amd64 |
| Daemon | Reachable by the backend runtime user; `docker version`, `info`, `ps` succeeded |
| Image tag | `phase6-acceptance:local-v1` — tag is informational only |
| Executed immutable image | `sha256:78c7f2fa233ebfc26669a41e52154c62ede5b0d16b821dd83ca2dc5aeab9fac5` |
| Container Python | 3.12.14, copied from an already-local runtime |
| Configured provider / model | OpenRouter / `qwen/qwen-2.5-coder-32b-instruct` |
| Reservation / attempts | USD 1 per attempt; initial plus at most one repair |

Docker Desktop was initially stopped and was started. Managed-shell access to the user's Docker configuration required approved runtime-user execution. The backend Python process then used its normal Docker abstraction successfully; no socket bypass or relaxed container policy was introduced.

No suitable Phase 6 image existed locally. The acceptance image was built with `docker build --network=none --pull=false`, using the already-local donor `voice_assistance-backend:latest` at immutable identity `sha256:0763bfc78d34603462d6b6027ca68de4b1a4e7eb85007b6310add81002b4cb32`. The final scratch image copies only CPython/its shared libraries, selected existing pure-Python pytest/mypy/Bandit dependencies, fixed adapters and independent tests. It excludes the donor application, site-packages, entrypoint, credentials and environment. No image/package was downloaded. This records local provenance, not an independent supply-chain or online vulnerability certification.

The first image probe honestly failed because pytest's existing `py.py` compatibility module had not been copied. Its failure evidence is retained in `artifacts/phase6-real-sandbox-probe-first-failure.json`. The local dependency was added; all checks were rerun. No test or restriction was weakened.

Actual image-internal SHA-256 values, not post-formatting build-source hashes:

| Image file | SHA-256 |
|---|---|
| `/adapter.py` | `0bf3e99aa2607f9b4e48327546d33746637a7579e784b7e0521030f1cc73d583` |
| `/legacy_adapter.py` | `8c07ad3dd21c9ffb57349e90ec1210b654cb90d309eaf1d35e2b6b364415b91a` |
| `/legacy/calc.py` | `91079634ac8eba9a2261a063dcce461e89adbca0eb3bc226a59c11496547d867` |
| `/acceptance/test_calc.py` | `bc36885d5cad329f60a18074a316c023fedbeae05f950e854688a5e9740f196d` |
| `/acceptance/test_security.py` | `92fcbf9b69d4a6a36505d1f5fcfc392406724224a21e9726fe4024c90a6de9bc` |

Both adapters accept scenario/inputs through stdin and return only output/side_effects. The image's legacy calculator implements the same imperative addition function as the pinned fixture; it is an embedded runtime copy, not a host-mounted source checkout. The target adapter resolves exactly one calculator in the approved target layout. Frozen expected values and normalization stay on the host. Build inputs were formatted after image creation; a rebuild must receive a new pin and new validation.

## Real job, gates and Git isolation

The user separately authorized the fixture/model scope, disposable ADMIN registration, and each specific G1/G2/G3 evidence package. All three decisions went through the existing authenticated gate decision API and GateService. No approved gate, workflow state or PASS result was inserted directly into the database.

| Evidence | ID / value |
|---|---|
| Job | `202f9e81-6c9a-4266-a6c1-06f099fd392d` |
| Runtime module | `82bba4e6-ecfa-5b89-8455-b82ae074ca1a` |
| Pinned source / branch base | `21ddf9efc6583c16ff0e8a2e4ae9862f2eb1cb09` |
| G1 approved | `75320b99-57c0-4bd4-9d9f-253bff28401c` |
| Frozen suite, version 2 | `8d2d87fb-617c-438b-92aa-6d805b08bb29` |
| Suite SHA-256 | `61d3df2fff20f725f43821ae195d00ad6244c20f0ebce506431db7bca6b000d7` |
| G2 approved | `7b8acf5b-804e-40f5-9d89-b57f5d3ce687` |
| Conversion plan, version 1 | `f8cbade9-5dea-49a6-a34b-c447d4e7583e` |
| Plan artifact | `e5d75765-e9b3-4175-ba0e-a6d1d666986d` |
| Actual plan artifact SHA-256 | `ff3b51ed68c98c19e9913a87260120661bbc8d6555e37f58eb9db0dedd88c38f` |
| G3 approved | `3dfb1e63-fb34-4889-8f89-8fca69389b4d` |
| Attempt 1 | `880c7e88-f90e-4bf9-8e82-ec331431cb52` |
| AgentRun | `bb24c8af-fbc3-4b3d-906e-a10478eec85c` |
| Branch | `job/202f9e81-6c9a-4266-a6c1-06f099fd392d/module/82bba4e6-ecfa-5b89-8455-b82ae074ca1a/attempt/1` |
| Worktree | `backend/repo_workspaces/phase6/880c7e88-f90e-4bf9-8e82-ec331431cb52` |
| Allowed target | `app/modules/job_202f9e81-6c9a-4266-a6c1-06f099fd392d_b66f39` |
| Final job / attempt disposition | PAUSED from CONVERTING / BLOCKED |

Intake used the existing development-local Git adapter and a runtime-user-owned disposable repository. An initial managed-user ownership conflict was resolved by making a separate fixture copy, not disabling Git ownership checks or altering global Git config. The branch/worktree exists at the pinned base commit; no model ChangeSet or changed-file hash exists.

The actual model request reached OpenRouter and returned **HTTP 402, insufficient credits / account never purchased credits**. No model output, request-success ID, usage, billed cost, model-backed verification, review or repair was returned. Database default zero counters are not presented as provider-reported usage. No substitute provider, fake generation, credit purchase or further real model request was used after the user's decision to leave this pending.

## Frozen baseline and G2 exit

Four approved integer cases ran twice through the real Phase 5 legacy adapter: `(1,2) -> 3`, `(-5,2) -> -3`, `(5,-8) -> -3`, `(0,0) -> 0`. Both output and `{count:1}` side effects matched. No normalization or known legacy bugs were recorded. The scope is integer scenario coverage, not branch/line coverage, invalid-type handling or proof of arbitrary equivalence.

The discovery-only suite v1 remains retained and its old G2 gate is INVALIDATED. Suite v2 has four frozen TestCase definitions. Schema/data analysis is NOT_APPLICABLE: no tables, connections or migrations; schema artifact v2 hash is `dec0407f5e88dcc2e244857415c4c434980dc2c9a190dd00c5c98be3da1d1a9f`. No production migration ran. Empty schema validation is not being claimed as populated-data validation.

G2 exit evidence:

- Real G2 approval froze the current suite and routed through Supervisor to PLANNING, then the normal Planner produced pending G3.
- The real conversion API returned HTTP 409 while G3 was pending. G2 approval alone did not authorize conversion.
- After separately approved G3, Supervisor created the attempt/worktree and called the real provider.
- Regression tests `test_g2_to_phase6_canonical_exit_proof[PENDING/REJECTED/APPROVED]` all pass. They prove pending/rejected G2 blocks Phase 6, rejection returns to CHARACTERIZING, and approved G2 enables canonical Planning. These automated fixtures are not presented as additional real human decisions.

## Real Docker execution

The following is a **trusted-code probe at the actual approved target path**, not CodeWriter output and not a successful module attempt. It compares against the four actual G2-frozen cases. Full bounded command outputs are in `artifacts/phase6-real-acceptance/environment.json`.

Container ID: `f840e40887acd39a076514a58b75cda45491742ac7f1fa937df452a5fae9df4b`.

Container name: `phase6-f74819df7d984d39aabba13b7fb596b4`.

Execution fingerprint: `fb821f91f0866c72f1bd34a8a6baf6987fb1dcba548938ab34c780dfc6036bb0`.

Environment evidence-file SHA-256: `791895e7713cab7f089f088d99f5b753458bc752ef6c27617ed63d35e66d4b98`.

| Category | Exact approved command | Exit | Duration ms | Result |
|---|---|---:|---:|---|
| Build | `python -m compileall -q .` | 0 | 396.986 | PASS |
| Unit | `python -m pytest /acceptance/test_calc.py -q -p no:cacheprovider` | 0 | 1612.005 | PASS, 6 independent cases |
| Static | `python -m mypy --cache-dir=/tmp/mypy-cache --check-untyped-defs --explicit-package-bases .` | 0 | 9576.336 | PASS, 1 target source file |
| Security | `python -m bandit -r . -q` | 0 | 921.296 | PASS |
| Isolation | `python -m pytest /acceptance/test_security.py -q -s -p no:cacheprovider` | 0 | 994.700 | PASS, 1 independent test |

Frozen comparison for this probe: total 4, executed 4, matched 4, mismatched 0, unobserved 0, blocked 0. Each adapter call has its command, exit code, duration and actual observation. The independent deterministic Reviewer v6.2 reports zero critical/high/medium/low findings for this trusted probe, with its limitation that untested semantics are not proven. **For the real CodeWriter attempt, none of these commands/cases/reviews executed.** It has zero TestResult rows and no converted/verification/review artifacts.

## Sandbox security evidence

Live `docker inspect` observed: NetworkMode none; ReadonlyRootfs true; UID/GID 65534; CapDrop ALL; no-new-privileges; Memory 268435456; NanoCpus 1000000000; PidsLimit 64; no Binds/Mounts; only bounded `/work` and `/tmp` tmpfs settings; AutoRemove true; log driver none. Image environment names are only PATH, PYTHONDONTWRITEBYTECODE and PYTEST_DISABLE_PLUGIN_AUTOLOAD.

In-container tests additionally confirmed loopback-only networking, failed connection to a documentation-only external address, read-only root writes, non-root IDs, zero effective capabilities, no-new-privileges, cgroup CPU/memory/PID bounds and absence of credential variables. Cleanup was checked after execution. Final `docker ps` contained no Phase 5/6 acceptance containers; the unrelated Redis container was left untouched.

Source travels through the existing JSON mechanism, not a host mount. The adapter/tests are image-owned and read-only. The harness keeps 30-second command timeouts, configured 180-second overall deadline and bounded serialized stdout/stderr; unit regressions also exercise deadline/output-overflow cleanup. This run did not perform a real 30-second timeout or resource-exhaustion stress test; those stress paths remain automated-test evidence, not live stress proof.

## Negative checks, APIs and audit

Five real Docker probes each prevented verification: syntax/build failure; subtraction causing unit and frozen behavior failures; wrong return annotation detected by mypy; `eval` detected by Bandit/Reviewer; zero executable cases remaining UNOBSERVED/non-passing. Each includes fresh checks, case observations and independent review in `negative-*.json` and `negative-summary.json`. These are labeled controlled probes, never forged CodeWriter attempts or successful repair evidence.

All eight Phase 6 routes were exercised using the real app/router/authorization/database through HTTPX ASGI transport, without auth dependency overrides: eight unauthenticated checks returned 401; eight authenticated nonmember checks returned 404; five owner read endpoints returned 200. Pending-G3 conversion and paused-job repair returned 409. A fabricated finding waiver returned 404, never an applied waiver. Four owner requests containing commands, argv, fabricated verification or `verified` fields returned 422. Positive real repair/waiver execution remains pending; existing unit tests cover those flows with explicitly labeled doubles.

The captured job event stream contains 23 events: JOB_CREATED 1; ARTIFACT_PUBLISHED 6; JOB_INTAKE_COMPLETED 1; WORKFLOW_TRANSITION 6; GATE_DECIDED 3; BASELINE_REVISION_RECORDED 2; CHARACTERIZATION_CAPTURED 2; MODULE_CONVERSION_QUEUED 1; MODULE_BLOCKED 1. Ten persisted artifacts were read and their actual bytes matched their stored SHA-256, retaining historical suite/schema versions. No G4 exists and no integration/archive artifact was fabricated. See `persistence.json` and `api-checks.json`.

## Targeted changes and gap matrix

| Requirement / audited gap | Action / evidence | Status |
|---|---|---|
| Real restricted Docker runtime | Offline image, live inspect, positive/negative real execution | PASS |
| Real legacy reproducibility and human G2 | Four twice-observed cases, hash-bound canonical human decision | PASS |
| Model identity/billing trace was incomplete | Existing ModelResponse/gateway/CodeWriter retain provider ID, model/usage metadata and reported cost; estimates explicitly labeled; regression tests | PASS for implementation, successful real response PENDING |
| Container identity was not retained | Existing sandbox reports actual generated container name and total duration | PASS |
| Reviewer did not inspect check evidence | Existing Reviewer consumes independent execution/check/case evidence and blocks incomplete/failing evidence | PASS on probes/regressions |
| Integrator fabricated success/usage/artifact metadata | Removed placeholder success path; now raises a safe conflict before writes or G4 transition | FAIL for actual integration capability; fail-closed safeguard PASS |
| Real CodeWriter ChangeSet and executable evidence | Provider HTTP 402; no substitution or fake PASS | PENDING |
| Clean-base real-model repair and exhaustion | No generated attempt reached verification; no retry after user stopped model acceptance | PENDING |
| Phase 6 route authentication/IDOR and unsafe inputs | Real authenticated API checks plus full unit regression | PASS for exercised checks |
| Complete positive execution/repair/waiver API chain | Cannot exercise successful model-dependent work while provider unfunded | PENDING |
| Manual browser board acceptance | Frontend tests/build pass; no browser automation tool available, no live manual `#/modules` acceptance claimed | PENDING |
| Global authorization readiness | Existing public registration accepts requested privileged roles; outside this targeted Phase 6 change, not a production RBAC sign-off | FAIL / requires security review |

Production code changed only in `phase6_sandbox.py`, `phase6_service.py`, `code_writer.py`, `model_gateway.py`, `reviewer_agent.py`, `integrator_agent.py`, and `schemas/agent_runtime.py`, plus the new `test_phase6_acceptance_gaps.py`. Existing gateway/schema files were formatted and narrowly type-corrected. New `tools/phase6_acceptance/` files are acceptance fixtures/drivers/image inputs, not new orchestration services. No duplicate tables, migrations, auth engine, gate engine or Supervisor were introduced. Shared backend `.env` and secrets were not changed; acceptance settings are process-local and use valid DEBUG=false.

## Final regression

| Check | Exact result / scope |
|---|---|
| Full backend, final run | **275 passed + 3 skipped = 278**, 0 failures/errors; `artifacts/phase6-real-backend-final.xml` |
| Existing Phase 6 subset | 33 passed + 1 skipped = 34, included in full total |
| New acceptance-gap regressions | 13 passed = 13, included in full total |
| Combined Phase 6 backend scope | **46 passed + 1 skipped = 47**, included in full total |
| Phase 5 backend | **48 passed + 1 skipped = 49**, included in full total |
| Other backend tests | 181 passed + 1 skipped = 182; 47 + 49 + 182 = 278 |
| Opt-in real Docker test, separate invocation | **1 passed**, `artifacts/phase6-real-docker-test.xml`; not added to the full-suite count |
| Full frontend | **39 passed / 6 files**; includes Phase 6 **9 passed**, Phase 5 **6 passed** |
| TypeScript / production build | PASS, `npm.cmd run build` (tsc + Vite) |
| Ruff | PASS, seven changed backend source files, new test and acceptance harness |
| Mypy | PASS, seven changed backend source files, explicit namespace-package roots / silent imported modules |
| Black | PASS, 25 source/test/harness files; offline copied dependencies excluded |
| Bandit | PASS, seven changed backend source files, zero unsuppressed findings |
| pip check | PASS, no broken requirements |
| Online dependency audit | NOT RUN; no online vulnerability-clean claim |

The three default backend skips are Windows symlink capability and the opt-in Phase 5/6 real-adapter tests. The Phase 6 real-adapter test was separately enabled and passed. The human-approved real Phase 5 capture ran outside the unit fixture. Earlier restricted-user test setup failed on existing Windows temp-directory ACLs; the final runtime-user suite used a fresh explicitly scoped temporary directory and passed. Existing 37 deprecation/resource warnings and the frontend >500 kB bundle warning remain visible, not silently suppressed.

Repository-wide `git diff --check` also reports existing extra EOF blank lines in `backend/app/models/__init__.py`, `backend/app/schemas/__init__.py` and `frontend/src/styles/main.css`. Those unrelated dirty files were preserved. The scoped lint/format PASS above is not a claim that the entire pre-existing worktree is clean.

## Remaining acceptance work

1. A funded credential for the user-approved model, followed by renewed direction to resume the paused job. No credit purchase, model substitution or retry is authorized by this report.
2. A successful real-model ChangeSet, complete verification/review artifacts and a genuine bounded repair/reverification/exhaustion proof. Keep current baseline/plan/gate hashes checked on resume.
3. Actual evidence-backed Git integration, system tests and delivery/G4 preparation. The previous fabricated success is disabled; integration is not implemented by this acceptance change.
4. Live browser board acceptance and the remaining positive real API actions. Address global privileged-registration/security concerns before any production sign-off.

All fixture evidence, versions, branch and the paused job are retained for audit. No material acceptance data was deleted, no production data was accessed, and no failing or missing execution was marked successful.
