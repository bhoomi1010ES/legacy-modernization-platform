# API Changes & Route Contract Specification
## Phase 1 Implemented REST Endpoints

**Document:** `docs/phase-1/api-changes.md`  
**Phase:** Phase 1 (API Implementation)  
**Date:** October 19, 2026  
**Status:** Completed & Verified  

---

## 1. Implemented Endpoints Reference

All endpoints reside under the versioned prefix `/api/v1`.

### 1.1 Authentication & Identity (`/auth`)
| Method | Path | Auth Required | Request Body | Response Body | Description |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `POST` | `/api/v1/auth/login` | No | `LoginRequest` (email, password) | `UserResponse` + Set-Cookie (`rebase_session_id`) | Authenticates bcrypt hash, rotates sessions, sets HttpOnly cookie. |
| `POST` | `/api/v1/auth/logout` | Yes | None | `SuccessResponse` (clears cookie) | Invalidates server session in PostgreSQL and unsets client cookie. |
| `GET` | `/api/v1/auth/me` | Yes | None | `UserResponse` | Returns authenticated user profile, roles, and effective permissions. |

### 1.2 Modernization Jobs (`/jobs`)
| Method | Path | Auth Required | Request Body | Response Body | Description |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/api/v1/jobs` | Yes (`job:read`) | Query: `limit`, `offset`, `status` | `JobListResponse` | Lists jobs for user with deterministic ordering (`created_at DESC`). |
| `POST` | `/api/v1/jobs` | Yes (`job:create`)| `JobCreateRequest` | `JobDetailResponse` | Transactionally creates `Job`, `JobMembership`, and initial `AuditEvent`. |
| `GET` | `/api/v1/jobs/{job_id}` | Yes (`job:read`) | None | `JobDetailResponse` | Retrieves job detail; verifies active job membership (or SUPER_ADMIN). |
| `POST` | `/api/v1/jobs/{job_id}/cancel` | Yes (`job:cancel`)| None | `JobDetailResponse` | Enforces state machine and cancels active job; records audit event. |
| `POST` | `/api/v1/jobs/{job_id}/pause` | Yes (`job:pause_resume`)| None | `JobDetailResponse` | Transitions active job to `PAUSED`. |
| `POST` | `/api/v1/jobs/{job_id}/resume` | Yes (`job:pause_resume`)| None | `JobDetailResponse` | Resumes paused job to `CONVERTING`. |

### 1.3 Artifact Deliverables (`/jobs/{job_id}/artifacts`)
| Method | Path | Auth Required | Request Body | Response Body | Description |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/api/v1/jobs/{job_id}/artifacts` | Yes (`artifact:read`)| Query: `artifact_type` | `ArtifactListResponse` | Lists versioned deliverables for authorized job. |
| `POST` | `/api/v1/jobs/{job_id}/artifacts` | Yes (`artifact:read`)| `CreateArtifactPayload` | `ArtifactResponse` | Publishes immutable artifact version with SHA-256 validation. |
| `GET` | `/api/v1/jobs/{job_id}/artifacts/{artifact_id}` | Yes (`artifact:read`)| None | `ArtifactResponse` | Retrieves artifact metadata and lineage array (`derived_from`). |
| `GET` | `/api/v1/jobs/{job_id}/artifacts/{artifact_id}/content` | Yes (`artifact:download`)| None | `ArtifactContentResponse` | Retrieves raw content and re-verifies cryptographic checksum. |

### 1.4 Append-Only Audit Trail (`/jobs/{job_id}/audit`)
| Method | Path | Auth Required | Request Body | Response Body | Description |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/api/v1/jobs/{job_id}/audit` | Yes (`audit:read`) | Query: `limit`, `offset`, `actor_type` | `AuditListResponse` | Returns chronological audit log for authorized job. |

### 1.5 System Probes (`/health`, `/readiness`, `/ready`)
| Method | Path | Auth Required | Request Body | Response Body | Description |
| :--- | :--- | :---: | :--- | :--- | :--- |
| `GET` | `/api/v1/health` | No | None | `HealthResponse` | Liveness probe verifying server and database connection. |
| `GET` | `/api/v1/readiness`| No | None | `ReadinessResponse` | Readiness probe; returns 503 if database ping probe fails. |
| `GET` | `/api/v1/ready` | No | None | `ReadinessResponse` | Alias for `/readiness` probe. |
