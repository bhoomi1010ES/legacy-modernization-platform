# API Contracts Specification: Multi-Agent Legacy Code Modernization Platform

**Document:** `docs/phase-0/api-contracts.md`  
**Phase:** Phase 0 (Discovery, API Contracts & Interface Architecture)  
**Date:** October 19, 2026  
**Status:** Completed  
**Author:** Principal Software Architect & Senior Backend Engineer  

---

## 1. API Design Principles & Standard Conventions

All APIs follow RESTful conventions under the versioned prefix `/api/v1`.

### 1.1 Error Envelope Specification
All error responses (4xx and 5xx) share a standardized JSON envelope:
```json
{
  "error": {
    "code": "INVALID_STATE_TRANSITION",
    "message": "Cannot transition job from CREATED to CONVERTING. Preconditions not met.",
    "request_id": "req_8f1a23c09b",
    "details": [
      {
        "field": "status",
        "issue": "Preceding stages (Analysis, Feasibility, Characterization) must complete first."
      }
    ]
  }
}
```

### 1.2 Pagination Standard
List endpoints support limit-offset pagination:
- `limit`: Number of items to return (default: 50, maximum: 100).
- `offset`: Starting item index (default: 0).
Response envelopes include `items`, `total`, `offset`, and `limit`.

---

## 2. API Contract Inventory

### 2.1 Authentication & User Endpoints

| Method | Path | Request Schema | Response Schema | Status Codes | Auth Required | Description |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| `POST` | `/api/v1/auth/login` | `LoginRequest` (email, password) | `UserResponse` | 200, 401, 422 | No | Authenticates user; sets HttpOnly session cookie. |
| `POST` | `/api/v1/auth/logout` | Empty | `SuccessResponse` | 200, 401 | Yes | Invalidates active session; clears cookie. |
| `GET` | `/api/v1/auth/me` | None | `UserResponse` | 200, 401 | Yes | Returns identity, global roles, and user details. |
| `POST` | `/api/v1/auth/change-password` | `ChangePasswordRequest` | `SuccessResponse` | 200, 400, 401 | Yes | Updates password and destroys all other sessions. |

### 2.2 Modernization Jobs Endpoints

| Method | Path | Request Schema | Response Schema | Status Codes | Auth Required | Description |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| `GET` | `/api/v1/jobs` | Query: `offset`, `limit`, `status` | `JobListResponse` | 200, 401 | Yes | Lists modernization jobs accessible to user. |
| `POST` | `/api/v1/jobs` | `JobCreateRequest` | `JobDetailResponse` | 201, 400, 401, 422 | Yes (`job:create`) | Submits a new modernization job. |
| `GET` | `/api/v1/jobs/{job_id}` | None | `JobDetailResponse` | 200, 401, 404 | Yes (`job:read`) | Retrieves detailed job status, budget, and config. |
| `POST` | `/api/v1/jobs/{job_id}/pause`| Empty | `JobDetailResponse` | 200, 401, 409 | Yes (`job:pause_resume`) | Pauses active modernization workflow. |
| `POST` | `/api/v1/jobs/{job_id}/resume`| Empty | `JobDetailResponse` | 200, 401, 409 | Yes (`job:pause_resume`) | Resumes paused modernization workflow. |
| `POST` | `/api/v1/jobs/{job_id}/cancel`| Empty | `JobDetailResponse` | 200, 401, 409 | Yes (`job:cancel`) | Cancels job and terminates active sandboxes. |

### 2.3 Artifacts Endpoints

| Method | Path | Request Schema | Response Schema | Status Codes | Auth Required | Description |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| `GET` | `/api/v1/jobs/{job_id}/artifacts` | Query: `artifact_type`, `version` | `ArtifactListResponse` | 200, 401, 404 | Yes (`artifact:read`) | Lists versioned deliverables for a job. |
| `GET` | `/api/v1/jobs/{job_id}/artifacts/{artifact_id}` | None | `ArtifactResponse` | 200, 401, 404 | Yes (`artifact:read`) | Retrieves artifact metadata, hashes, and lineage. |
| `GET` | `/api/v1/jobs/{job_id}/artifacts/{artifact_id}/content` | None | `ArtifactContentResponse` or Raw | 200, 401, 404 | Yes (`artifact:download`) | Retrieves authorized artifact payload or JSON content. |

### 2.4 Human Approval Gates Endpoints

| Method | Path | Request Schema | Response Schema | Status Codes | Auth Required | Description |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| `GET` | `/api/v1/gates/pending` | Query: `offset`, `limit` | `PendingGatesResponse` | 200, 401 | Yes (`gate:review`) | Lists all pending approval gates across jobs. |
| `GET` | `/api/v1/jobs/{job_id}/gates` | None | `GateListResponse` | 200, 401, 404 | Yes (`gate:review`) | Lists all gates (G1–G4) and historical decisions for a job. |
| `GET` | `/api/v1/jobs/{job_id}/gates/{gate_id}` | None | `GateDetailResponse` | 200, 401, 404 | Yes (`gate:review`) | Retrieves gate evidence, status, and required options. |
| `POST`| `/api/v1/jobs/{job_id}/gates/{gate_id}/decisions` | `GateDecisionRequest` | `GateDecisionResponse` | 200, 400, 401, 403, 409, 422 | Yes (`gate:approve_*`) | Submits human approval or rejection with written rationale. |

### 2.5 Agent Execution & Tracing Endpoints

| Method | Path | Request Schema | Response Schema | Status Codes | Auth Required | Description |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| `GET` | `/api/v1/jobs/{job_id}/agents` | None | `AgentRunListResponse` | 200, 401, 404 | Yes (`job:read`) | Lists specialist agent runs and active workers. |
| `GET` | `/api/v1/jobs/{job_id}/agents/{run_id}` | None | `AgentRunDetailResponse` | 200, 401, 404 | Yes (`job:read`) | Retrieves step execution trace, tokens, and model details. |

### 2.6 Audit & Verification Reports Endpoints

| Method | Path | Request Schema | Response Schema | Status Codes | Auth Required | Description |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| `GET` | `/api/v1/jobs/{job_id}/audit` | Query: `offset`, `limit`, `actor_type` | `AuditListResponse` | 200, 401, 404 | Yes (`audit:read`) | Retrieves immutable chronological audit log. |
| `GET` | `/api/v1/jobs/{job_id}/reports/verification` | None | `VerificationReportResponse` | 200, 401, 404 | Yes (`job:read`) | Retrieves equivalence metrics and classified test outcomes. |
| `GET` | `/api/v1/jobs/{job_id}/reports/delivery` | None | `DeliveryReportResponse` | 200, 401, 404 | Yes (`job:read`) | Retrieves final delivery readiness package and PR links. |

### 2.7 System & Health Endpoints

| Method | Path | Request Schema | Response Schema | Status Codes | Auth Required | Description |
| :--- | :--- | :--- | :--- | :---: | :---: | :--- |
| `GET` | `/api/v1/health` | None | `HealthResponse` | 200 | No | Returns system health and database connectivity. |
| `GET` | `/api/v1/readiness` | None | `ReadinessResponse` | 200, 503 | No | Kubernetes readiness probe (checks DB, S3, workers). |
| `GET` | `/openapi.json` | None | OpenAPI Specification v3.1 | 200 | No | Emits standard machine-readable API documentation. |
