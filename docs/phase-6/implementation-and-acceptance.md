# Phase 6: implementation and acceptance

> The implementation-time environment snapshot below is historical. The subsequent [real-environment acceptance report](../phase6/PHASE6_REAL_ENVIRONMENT_ACCEPTANCE.md) supersedes its runtime status: Docker now executes real checks; the approved model request returned HTTP 402, and the Integrator placeholder was replaced with a fail-closed boundary. Integrated acceptance remains open.

## Scope and architecture

The attached implementation plan was used as workflow reference. The user's canonical order remains authoritative:
G1 -> Characterization -> Schema/Data -> human G2 -> Planning -> human G3 -> Conversion -> Verification -> Integration -> human G4.

Supervisor owns queueing, dependency waves, parallel worker dispatch, bounded repair, module disposition and workflow transitions. CodeWriter cannot approve gates or attest verification. Existing Module/ModuleAttempt, AgentRun, Artifact, TestCase/TestResult and AuditEvent tables are reused; no migration is required.

| Requirement | Audited gap | Implementation/evidence |
|---|---|---|
| Real CodeWriter | Previous worker generated generic templates and synthetic usage | Versioned prompt, allowlisted existing model gateway, strict ChangeSet, actual returned usage, bounded context/output/task reservation |
| Scoped isolation | Branch names were metadata only | Git worktree/branch per attempt, pinned source commit, approved plan paths, protected tests/config, verified dependency artifacts; no host repository code execution |
| Independent verification | Artifact presence previously counted as PASS | Trusted image adapter, real sandbox build/unit/static/security commands and host-side frozen-output/side-effect comparison; unavailable runtime blocks |
| Review | No independent Reviewer | Versioned static security/stub/contract/unsupported-claim findings, severities and exact artifact references; limitations are explicit |
| Bounded repair | One generic retry could still emit success | Exact prior evidence, new clean-base worktree, all executable frozen cases rerun, prior results invalidated, repeated failure/max-attempt escalation |
| Immutable history | Some artifacts had metadata without stored bytes | Existing ArtifactService stores canonical JSON/SHA-256, separate code/verification/review artifacts; old attempts and branches retained |
| Canonical orchestration | Conversion could unconditionally advance | Current G1/G2/G3, frozen baseline and approved plan checked before execution and disposition; integration requires actual evidence for every module |
| APIs/RBAC | Eight Phase 6 APIs absent | All eight routes, job membership/anti-IDOR reuse, explicit convert/repair/waiver capabilities, audit trail; no caller commands or results |
| UI | Execution board absent | `#/modules`: job/status filters, blockers, branch/attempt history, safe diff, checks, review and rationale-bound actions |
| Phase 4 bridge | Runtime materialization used nonexistent planning-unit fields | Materialize canonical source/target scopes and waves; source identifiers resolved to inventory paths; existing CamelCase plan artifact supported |

## Configuration (administrator only)

Defaults intentionally disable execution. Configure an allowlisted provider/model through the existing model gateway using `PHASE6_MODEL_PROVIDER` and `PHASE6_MODEL_IDENTIFIER`; provider keys remain server-side. Production execution refuses the fake provider.

Set `PHASE6_SANDBOX_IMAGE` to an already-installed, trusted Linux image containing Python, target tools/dependencies, independent tests and an adapter. Local image inspection pins its immutable image ID. No image is pulled automatically and no dependency installation/network access is enabled.

The target adapter is selected by `PHASE6_TARGET_COMMAND_JSON`, for example `["python", "/adapter.py"]`. It is part of the read-only image, not a generated `/work` or `/tmp` file. Its working directory is `/work`. It receives one JSON object on stdin:

```json
{"scenario": "add", "inputs": {"x": 1, "y": 2}}
```

It must write exactly `{"output": ..., "side_effects": ...}`. The host holds frozen expected values and normalization rules; these are not sent to the container. Merely discovering an unexecuted test never supplies a baseline assertion. Such frozen coverage gaps remain listed in `unobserved_cases` rather than being reported as executed.

`PHASE6_CHECK_COMMANDS_JSON` is an array of administrator-approved `{category, command}` objects. All four categories (`build`, `unit`, `static`, `security`) are mandatory. Commands must be appropriate for the approved target stack and cover the module/contracts; a zero exit code from an irrelevant command is not a substitute for meaningful project checks. Python `-m` tools, supported direct checking tools and explicitly named npm scripts are allowed; arbitrary shells, installation and caller-supplied commands are not. CodeWriter's suggested commands are recorded but never executed automatically.

Sandbox limits: no network, host mounts or production credentials; read-only root, unprivileged UID/GID, all capabilities dropped, no-new-privileges, 1 CPU, 256 MiB memory, 64 PIDs, bounded output, 30-second individual commands, bounded total deadline, named-container cleanup. Code is transferred as JSON into bounded disposable tmpfs, never mounted from the host. Repository snapshots currently support tracked UTF-8 files up to 8 MiB, generated changes up to 1 MiB and model context up to 256 KiB. Unsupported/binary/oversized/secret-bearing workspaces fail closed and require an appropriate reviewed module/environment plan.

Read-only model/agent versions, actual command/exit/duration, image identity, source/target commit, baseline/plan/code/evidence hashes, changes, notes and repair evidence are retained. Review is deterministic static review plus executed test evidence, not a proof of arbitrary untested semantics. Findings block verification. Waiver endpoints request audited human review only; they do not override tests or silently mark a module verified.

## Acceptance boundary

Automated tests use a scripted gateway and explicitly labeled container doubles. Trusted Python fixture checks are genuinely executed in subprocesses, but **are not Docker acceptance**. The opt-in real adapter test requires `PHASE6_RUN_REAL_ACCEPTANCE=1` and a configured local image/adapter/checks.

Current environment: Docker CLI is installed, but its daemon pipe is unavailable; Phase 6 model/image/adapter/check-command settings are absent. No real legacy/converted scenario, production migration or external model call was performed during implementation. **REAL SANDBOX ACCEPTANCE = PENDING ENVIRONMENT.** Do not treat this as a production execution sign-off.

## Final verification (23 October 2026)

| Check | Result | Scope/evidence |
|---|---|---|
| Full backend regression | PASS: 262 passed, 3 skipped, 265 total | `artifacts/phase6-backend-regression.xml`; all 265 cases collected, no failures/errors |
| Phase 6 backend subset | PASS: 33 passed, 1 skipped, 34 total | `backend/tests/test_phase6.py`; included in the full total, not additional tests |
| Phase 5 regression subset | PASS: 48 passed, 1 skipped, 49 total | Existing characterization/gate tests retained in full run |
| Full frontend | PASS: 39 passed, 0 failed | Six test files; includes all 9 Phase 6 frontend tests |
| TypeScript and production build | PASS | `npm.cmd run build` (tsc + Vite); existing bundle-size warning remains |
| Python lint | PASS | Ruff on Phase 6 services/schema/API/tests |
| Python type check | PASS | Mypy, 8 Phase 6 source files; imported legacy modules checked silently |
| Python formatting | PASS | Black check, 9 implementation/test files; no changes needed |
| Static security | PASS | Bandit on 7 Phase 6 implementation files; no unsuppressed findings; verdict-enum password false positive specifically annotated |
| Installed Python dependencies | PASS | `pip check`: no broken requirements |
| Frontend dependency audit | PARTIAL | Offline npm audit reported zero cached advisories; no fresh online advisory check claimed |
| Real sandbox execution | PENDING ENVIRONMENT | Daemon unavailable and model/image/target-adapter/check commands unconfigured; zero real scenarios executed |

The three backend skips are the Windows symlink-creation capability test and the explicitly configured Phase 5 and Phase 6 real-adapter acceptance tests. Existing deprecation/resource warnings remain visible in the regression output; the suite is passing, not warning-free.

Important executable proofs in `test_phase6.py`: pending/rejected/stale G1/G2/G3 block conversion; frozen-suite comparisons detect regression; missing execution never verifies; exact repair evidence creates a separate branch, invalidates old results and reruns the frozen suite; repeated/max-attempt failures escalate; cross-job access is denied; all eight APIs are exercised; waiver requests never apply themselves; the Supervisor pool reaches INTEGRATING only after independent execution/review. Transitive dependency files are hydrated in dependency order and stale plan evidence is rejected. Old tests that treated metadata/forced flags as execution were replaced with executed fixtures or explicit evidence-boundary assertions.

Changed implementation is limited to Phase 6 services/schema/API/prompt and the module-execution UI, plus targeted Supervisor/scheduler/RBAC/router/Phase 4 planning bridges, API registration, model-gateway output limits, environment template, tests and this document. No new persistence tables or production migrations were introduced. Existing unrelated worktree changes are preserved.

PHASE 6 IMPLEMENTATION COMPLETE — REAL ENVIRONMENT ACCEPTANCE PENDING.
