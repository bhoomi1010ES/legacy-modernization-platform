# W09 Acceptance Report: New Output Folder Delivery

**Date:** 2026-10-30  
**Decision assessed:** Preserve the uploaded source repository and write the modernized project to a separate, job-scoped output workspace, then deliver it as a ZIP.  
**W09 status:** IN PROGRESS — this architecture can satisfy the no-commit requirement, but the required real provider and sandbox evidence has not been collected.

## Executive summary

Writing converted code to a new output folder means the user's uploaded repository does not need to be edited or receive conversion-time Git commits. That removes the need to apply conversion changes back to the user's source checkout.

It does **not** remove the need for a bounded `ChangeSet`. The platform still needs to constrain which files an agent may create or change, bind those changes to the approved plan, verify exactly what was produced, and record auditable file-level provenance. A textual Git diff is not a W09 acceptance requirement by itself, but the existing temporary diff evidence should be retained while the workflow uses it. It may describe the candidate's changes relative to the pinned source snapshot; it must not be applied to or committed in the uploaded repository.

The output folder must itself be an isolated job/attempt workspace. It must not be a shared writable folder or a directory where generated code runs on the API host. The final verified output remains a ZIP artifact with a SHA-256 and linked modernization manifest.

## Recommended data flow

```text
Uploaded repository (read-only snapshot, pinned source SHA)
                 |
                 +--> analysis and source references
                 |
                 +--> per-job candidate output workspace
                         ^ bounded, validated ChangeSets
                         | applied by control service; never executed there
                         v
                   separate sandbox worker
                         |
             build + unit + security + characterization
                         |
                  verified candidate tree
                         |
                  ZIP + manifest artifacts
                         |
                authorized job download
```

The input snapshot remains immutable. The output candidate is assembled in a new job-scoped folder initialized from the approved source snapshot, or from an explicitly defined generated-project template if the product intends a from-scratch conversion. The choice between those two inputs must be fixed in the approved plan and recorded in the manifest; otherwise "complete project" is ambiguous.

## Is a diff still needed?

| Capability | Needed with a separate output folder? | W09 treatment |
|---|---|---|
| Git source reading and pinned baseline SHA | Yes | Retain for provenance and reproducible analysis. |
| Bounded, schema-validated ChangeSet | Yes | Retain; validate paths and module scope before writing to the output workspace. |
| Git commit to uploaded repository | No | Prohibit in conversion, verification, integration, and packaging. |
| Git diff applied to uploaded repository | No | Never apply it to the source checkout. |
| Temporary diff/equivalent change evidence | Retain while current services rely on it | Keep as an audit/review representation of the candidate delta, alongside changed-file names and before/after hashes. It is evidence only. |
| Complete ZIP and manifest | Yes | Required final delivery artifacts. |

The current workflow already reads and pins Git source and, after the recent changes, applies ChangeSets in isolated Git worktrees without conversion commits. Moving to a non-Git output directory would be an implementation change; it must preserve those read, source-pinning, ChangeSet-scope, and audit functions. Do not remove temporary diff functionality until every consumer and evidence contract has been migrated.

## W09 pass criteria for this design

### 1. Source preservation and candidate workspace

- Capture the source repository reference and exact baseline SHA.
- Make the source snapshot read-only to conversion and execution workers.
- Create a fresh, job-scoped output workspace; keep attempts isolated and avoid shared writable worktrees.
- Validate every ChangeSet path and reject traversal, absolute paths, symlinks, devices, hidden control paths, and out-of-scope writes.
- Record ChangeSet ID, attempt ID, allowed scope, changed/generated file list, source baseline, and file/diff hashes.
- Acceptance evidence shows the uploaded source tree and pinned source SHA are unchanged after conversion.

### 2. Real provider and budget evidence

- Use an approved provider/model on an isolated test account with a provider-side spend limit.
- Generate a real bounded ChangeSet through the production gateway path; a direct provider connectivity check or mocked response is insufficient.
- Record request ID, provider, actual model, prompt revision, token use when returned, estimated cost, billed/reported cost, retries, and rate-limit responses.
- Demonstrate reservation before dispatch, reconciliation afterward, stopping at the ceiling, and duplicate-charge safety across retries/process recovery.
- Verify the resulting ChangeSet is valid and applies only to its approved output-workspace scope.

### 3. Separate sandbox and hostile-code evidence

- Execute candidate code on a separate worker. The API/control plane must not execute it.
- The worker has no control-plane DB credentials, cloud credentials, or Docker socket; generated code cannot access another job's workspace or artifacts.
- Verify the actual runtime and image digest on the worker. Enforce non-root execution, resource/time limits, read-only root, scratch space, no privilege escalation, seccomp and AppArmor/SELinux or equivalent, and default-deny networking.
- Run and retain results for path/symlink escape, host-secret and Docker-socket access, cloud metadata, cross-job file access, fork bomb, infinite loop, network egress, unexpected dependency installation, and process-tree cancellation tests.
- Demonstrate job/attempt cleanup and scheduled cleanup of abandoned workspaces without deleting retained audit logs.

### 4. Independent verification and ZIP delivery

- Independently run target build, unit, security, schema where applicable, and frozen characterization checks in the sandbox against the exact candidate tree.
- Package the complete candidate, excluding `.git`, platform state, secrets, credentials, temporary files, and unsafe paths.
- Validate ZIP entries and CRC, calculate SHA-256, and store the ZIP as a job-scoped artifact.
- Store a linked manifest with job/source reference and baseline SHA, target stack, ChangeSet and attempt IDs, modified/generated files, verification results, ZIP artifact ID/hash, and packaging time.
- Bind G4 approval to the exact ZIP, manifest, report, SBOM, and verification hashes. Confirm that an authorized user can download the ZIP and a different job cannot.
- Confirm no Git commit is created during any conversion, verification, integration, or packaging step. Source Git history remains available for reading and provenance.

## Existing repository evidence and gaps

- `phase6_workspace.prepare` creates per-attempt Git worktrees from a pinned source SHA. `apply_changes` now records a base SHA and staged diff hash without creating a Git commit.
- Phase 7 now overlays verified ChangeSets into a detached candidate, packages the candidate ZIP, validates CRC and SHA-256, creates a manifest artifact, and exposes job-authorized artifact download. G4's required artifact set includes the ZIP and manifest.
- Focused W09 and Phase 7 failure-path checks now report **17 passed, 1 skipped**; canonical artifact-type normalization reports **1 passed**. The ZIP symlink test is skipped on this Windows host because it lacks symlink creation privilege. Affected Python modules compile successfully.
- These are implementation/unit checks, not complete W09 acceptance. One authorized real-provider conversion reached ChangeSet publication, but sandbox execution, separate-worker security, hostile-code containment, and end-to-end user ZIP download remain unproved.
- The current sandbox starts Docker from the application process. This does not satisfy the separate, credential-free execution-worker requirement. Docker is now reachable for inspection, but its reported runtime does not satisfy the platform's rootless/gVisor execution policy.
- The Phase 7 real-acceptance test has been updated for ZIP/manifest delivery and explicitly checks source immutability, no conversion commit evidence, ZIP CRC/hash, and the legacy delivery endpoint's ZIP response. The key is loaded. A process-scoped, authorized real-provider run reached CodeWriter ChangeSet validation, applied it in the isolated attempt workspace, and published its artifact; Phase 6 then blocked at the sandbox's non-rootless runtime check before executing generated code.

### Verification rerun (2026-10-30)

- Python compilation of the affected Phase 6/7 services and W09/Phase 7 tests passed.
- The project virtual environment (`backend/.venv`) already contains the pinned `pytest-asyncio==1.4.0`; system Python does not. The Phase 7 real-acceptance module collects **2 tests** under the venv.
- `backend/tests/test_w09_codewriter_sandbox.py` and `test_phase7_failure_paths_and_governance_invariants` under the project venv: **17 passed, 1 skipped**. The skipped ZIP symlink case requires Windows symlink privilege unavailable to this worker. Canonical artifact-type normalization: **1 passed**.
- Phase 6 queue leasing now uses and validates the lease owner returned by the scheduler; legacy artifact types are normalized through explicit known aliases, with unknown types still rejected. The fixture now supplies the normalized plan and approval records required by the current scheduler contract.
- Docker daemon is reachable with the approved local Docker access. It reports server `29.6.2`, Linux `x86_64`, `seccomp`/`cgroupns`, and `runc`; the daemon does not report rootless mode and no `runsc` gVisor runtime is available. The W09 sandbox's `verified_runtime_args()` therefore refuses execution under its current `docker-unverified` policy, as intended. Local Phase 6/7 acceptance images are present.
- A harmless smoke command in the pinned Phase 7 image succeeded with network disabled, read-only root, memory/CPU/PID limits, dropped capabilities, `docker-default` AppArmor, no-new-privileges, non-root UID 65534 and scratch tmpfs. This is only proof that the local image starts under those flags; it did not execute generated code and is not hostile-code containment evidence. The app's current `--blkio-weight=100` option failed on this daemon because `/sys/fs/cgroup/.../io.weight` is unavailable. The explicit `seccomp=default` selector also failed because Docker interpreted `default` as a profile file. The sandbox launcher now relies on Docker's reported built-in seccomp default and verifies that the daemon reports seccomp; I/O-limit incompatibility remains a fail-closed host limitation.
- The backend venv loads a non-empty `OPENAI_API_KEY` from `.env`; the value was not printed. The persisted `REAL_MODEL_SANDBOX_ENABLED` remains `false` and the configured default `MAX_BUDGET_USD` is `$5.00`.
- After explicit user authorization to send the synthetic acceptance fixture prompt/source to OpenAI, one real CodeWriter request ran with process-only overrides of `REAL_MODEL_SANDBOX_ENABLED=true`, `MAX_BUDGET_USD=$0.10`, `PHASE6_MAX_TASK_COST_USD=$0.10`, and `PHASE6_MAX_OUTPUT_TOKENS=512`. The gateway accepted the response and the workflow reached sandbox verification, so the returned charge stayed within its reservation. The disposable pytest database did not export a standalone usage/request-ID evidence record, so persistent budget/retry acceptance remains open. No other real-provider request was made.
- Sandbox execution failed closed with `Docker daemon does not report rootless mode`. Generated code did not execute. The host also lacks gVisor and cannot apply the configured I/O weight, so this run proves neither sandbox containment nor independent verification.
- `git diff --check` on the touched acceptance/report files passed.

## Implementation update (2026-10-30)

- The focused ChangeSet test now creates a distinct per-attempt output worktree and asserts generated files are present only there, the source checkout remains clean, both HEADs remain pinned to the same baseline SHA, and no commit identity is returned. This verifies the new-output-folder behavior while preserving the required temporary diff evidence.
- Phase 7 real-acceptance assertions and test descriptions now require a candidate tree hash, ZIP artifact and SHA-256, manifest artifact, valid ZIP CRC, source checkout unchanged, and ZIP delivery response. The legacy-named delivery API is tested only as a compatibility surface; branch creation and external PR publishing remain disabled.
- Artifact tamper coverage now includes the ZIP and modernization manifest. The implementation converts storage-integrity failures into a blocked/stale-package conflict.
- Remaining W09 blockers: persist the provider request/usage/cost/retry evidence; implement the separate credential-free worker; provide a runtime with verified rootless or gVisor isolation plus required I/O limits; run hostile-code probes and independent verification; and exercise authorized end-to-end ZIP download. The full Phase 7 E2E remains blocked at sandbox verification, so W09 is still **IN PROGRESS**.

## Suggested acceptance run sequence

1. Prepare a disposable database, object store, provider test account, and dedicated pytest temp directory outside tracked repository paths.
2. Verify a low-cost provider request through the gateway and capture request/usage/cost evidence.
3. Deploy the separate sandbox worker and verify its runtime/image and credential boundaries.
4. Run hostile fixtures; preserve tool output and worker audit events for each probe.
5. Run real bounded CodeWriter conversion and independently verify the generated candidate.
6. Confirm the source snapshot is unchanged and no conversion-time Git commit exists.
7. Package ZIP/manifest, verify their recorded hashes, exercise authorized and cross-job download checks, and submit those exact hashes for G4.
8. Review the evidence ledger and report W09 as passed only if every acceptance condition has a successful, reproducible run.

## Conclusion

The separate output folder is compatible with W09 and clarifies that conversion must not mutate the user's repository. It does not waive the requirements for bounded ChangeSets, a real provider request with persistent budget/retry safety, isolated sandbox execution, hostile fixture containment, independent verification, ZIP integrity, manifest lineage, and secure download. W09 must remain **IN PROGRESS** until the acceptance run above has real evidence.

### W09 follow-up (2026-11-02)

- Added `model_gateway_budgets` and `model_gateway_requests` as persistent accounting. Paid calls reserve against a database row before provider dispatch, persist request/provider/model/prompt identity, attempt and rate-limit counts, token usage, billed and estimated cost, and actual model/provider request ID. A request ID already in the ledger cannot be dispatched again after restart. Calls without a durable request identity are rejected. Ambiguous failures and responses without provider usage retain the reservation in `UNKNOWN` instead of releasing spend capacity. The local database is migrated to `d9e0f1a2b3c4`.
- Paid provider calls remain disabled unless the real-model feature flag is enabled. Real providers do not retry ambiguous failures by default; retries require an explicit provider idempotency capability. Deterministic fake-provider tests continue to use the non-production in-memory tracker.
- CodeWriter pre-allocates an attempt's model budget across its initial request and any bounded fallback chunks, so chunking cannot multiply the full attempt reservation. Paid responses without provider usage are retained as unresolved rather than reconciled as zero.
- Fixed ZIP member ordering: bytes are now written in canonical sorted path order, matching the validated manifest inventory. The W09 suite had caught valid trees whose filesystem traversal order differed from that inventory.
- Linux WSL verification after the changes: focused W09 suite **23 passed**; changed Python modules compiled; Alembic reported `d9e0f1a2b3c4` as its unique head; the local development database upgraded from `b10c0de5f678`; backend and frontend proxy health report PostgreSQL connected. The selected WSL Docker daemon reported `rootless` and `seccomp`, and the pinned Phase 6 image passed a no-network, read-only-root, resource-limited, non-root smoke command.
- W09 remains **IN PROGRESS**. The API/control process still invokes Docker directly; it has not been separated from Docker-socket authority or moved behind a separately leased, credential-free sandbox worker. No real paid provider acceptance was run in this follow-up. Hostile-code containment, process-tree cancellation, cross-job isolation, image scanning, ingress/submodule defenses, isolated dependency egress, human reconciliation UI for `UNKNOWN` charges, and end-to-end ZIP download authorization still require real execution evidence. A container smoke command is not that evidence.
