# Known Gaps, Security Boundaries & Phase 2 Roadmap
## Phase 1 Explicit Architectural Boundaries

**Document:** `docs/phase-1/known-gaps.md`  
**Phase:** Phase 1 (Known Gaps & Future Scope)  
**Date:** October 19, 2026  
**Status:** Completed  

---

## 1. Explicit Scope Boundaries (Phase 1 Invariants)

Per the Master Implementation Prompt, the following capabilities were **strictly excluded** from Phase 1 and will be introduced in subsequent phases:

| Feature / Domain | Current Status | Target Phase | Rationale & Boundary |
| :--- | :--- | :---: | :--- |
| **LLM Reasoning & Agent Calls** | Excluded | Phase 2 | Phase 1 focuses exclusively on deterministic persistence, Git intake, and identity. No LLM tokens were consumed. |
| **Autonomous Agent Orchestration** | Excluded | Phase 2 | LangGraph supervisor loops and multi-agent coordination deferred to Phase 2. |
| **Legacy Code Compilation & Execution** | Excluded | Phase 2 | No submitted source code or maven build scripts are executed on intake to ensure total host safety. |
| **Container Sandboxing (gVisor/Docker)** | Excluded | Phase 2 | Host process isolation via gVisor rootless containers scheduled for Phase 2 code execution. |
| **Remote Git Push to Production** | Excluded | Phase 3 | Pushing integration PR branches to upstream GitHub/GitLab repositories deferred until verification engine is complete. |
| **Database-Level Immutable Trigger** | Partial | Phase 2 | Audit immutability is currently enforced at the application/service layer. Direct database administrator access could theoretically alter records without a hardened DB role or cryptographic ledger. |

---

## 2. Identified Minor Gaps & Recommended Remediations

1. **Persistent Audit Database Role:**
   - *Risk:* Application code cannot update or delete audit events, but an administrative database user can execute raw SQL `DELETE FROM audit_events;`.
   - *Remediation (Phase 2):* Create a dedicated PostgreSQL database user for normal application runtime (`rebase_app`) with only `INSERT, SELECT` grants on `audit_events`.
2. **MinIO / AWS S3 S3StorageAdapter Implementation:**
   - *Risk:* Local filesystem storage is currently used. In distributed multi-worker environments, workers must share an S3 bucket or MinIO cluster.
   - *Remediation (Phase 2):* Provide `S3StorageAdapter` using `aioboto3` or `minio` SDK when cloud deployment is initiated.
3. **Double-Submit CSRF Token Middleware:**
   - *Risk:* `SameSite=Lax` cookie policy and custom `Content-Type: application/json` requirement block cross-origin HTML form POST attacks. Adding explicit CSRF tokens provides additional protection for non-JSON mutations.
   - *Remediation (Phase 2):* Introduce an `X-CSRF-Token` header handshake on session initialization.
