# W01 — Remaining Platform Risks and Next Workstreams

> **Document Type:** Remediation Risk Register & Handoff Brief  
> **Prepared:** 2026-10-30  
> **Current Milestone Completed:** W01 (Emergency Authentication, Authorization & Gate Integrity)  
> **Next Milestone:** W02 (Intake, Merkle Fingerprints & Repository Isolation)  

---

## 1. Status of W01 Scope

All direct W01 security targets (`SEC-01`, `SEC-02`, `SEC-03`, `SEC-04`, `SEC-05`, `SEC-08`) have been resolved and verified with regression tests.

No authentication bypass shortcuts remain in the codebase. Public registration is locked to least-privilege `DEVELOPER`. Job creators do not receive automatic `ADMIN` elevation. Job creators cannot approve their own gates. Unauthenticated stack scanning and SSRF/local system path probing are blocked. `TrustedHostMiddleware` and strict CSRF origin validation are active.

---

## 2. Catalog of Remaining Risks (Mapped to Future Workstreams)

The following items from the master remediation ledger (`REMEDIATION_EVIDENCE_LEDGER.md`) remain open and will be systematically remediated in their designated workstreams:

| Issue ID | Risk Summary | Target Workstream | Current Risk Level | Mitigation in Place Prior to Workstream |
|---|---|:---:|:---:|---|
| `SEC-06` | Production model secrets and default secret keys present in root `.env` | `W13` / Ops | `P0` | Production validator enforces `len(SECRET_KEY) >= 32` and rejects development keys when `ENVIRONMENT=production`. Secret values redacted in logging and audits. |
| `SEC-07` | Diagnostic artifact uploads unrestricted for internal schemas | `W06` / `W07` | `P0` | `POST /jobs/{job_id}/artifacts` requires `artifact:publish_diagnostic` and explicitly rejects workflow-owned artifact types (`REPOSITORYSNAPSHOT`, `LEGACYMODEL`, etc.). Full hash lineage verification planned in W06/W07. |
| `FLOW-01` | Serial module execution in supervisor router | `W04` / `W05` | `P1` | Workflow state machine enforces serial transitions safely without race conditions. Dynamic wave-based parallelization scheduled for W04/W05. |
| `FLOW-02` | Outbox message polling latency and retry backoff | `W07` | `P1` | Outbox items are persisted transactionally with status tracking. Background dispatcher optimization in W07. |
| `DATA-01` | Missing Merkle snapshot fingerprint validation on local uploads | `W02` | `P0` | Basic zip validation and staging directory isolation active in `LocalSourceAdapter`. Complete Merkle tree validation in W02. |
| `DATA-02` | Missing artifact lineage referential integrity foreign keys | `W07` | `P1` | Application-level validation verifies derived artifact references; database foreign key and cascading constraints in W07. |
| `DATA-03` | Checkpoint history gaps during failed recovery attempts | `W07` | `P1` | Checkpoints are committed atomically with transitions. Automated checkpoint rollback verification in W07. |
| `TEST-01` | Test suite database contention against non-isolated instances | `W01` / `W08` | `Resolved` | Conftest now enforces `TEST_DATABASE_URL` against `rebase_test_w01` with explicit isolation guard. |
| `UI-01` to `UI-05` | Frontend presentation, gate approval UI, and toast notifications | `W10` – `W12` | `P2` | Backend APIs return well-structured error envelopes (`ErrorEnvelope`) and ISO-8601 timestamps, ready for UI integration. |

---

## 3. Immediate Constraints for W02 Handoff

1. **Persistent Database Preservation:** Persistent database `rebase` must remain strictly untouched.
2. **Baseline State:** Baseline commit remains `3e69b506a3149509d791120ae785d0c1e4bed2a1` plus W01 remediation commits.
3. **Continuous Regression Testing:** All future workstreams must execute `pytest backend/tests/test_w01_security.py` as a prerequisite gate to guarantee zero security regressions.

