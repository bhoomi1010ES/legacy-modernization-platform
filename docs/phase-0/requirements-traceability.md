# Requirements Traceability Matrix: Phase 0 Architecture & Contracts

**Document:** `docs/phase-0/requirements-traceability.md`  
**Phase:** Phase 0 (Discovery, Architecture, Contracts & Foundation)  
**Date:** October 19, 2026  
**Status:** Completed  
**Author:** Principal Software Architect & QA Lead  

---

## 1. Overview & Classification Scheme

This Requirements Traceability Matrix tracks every functional, architectural, security, and verification requirement for Phase 0 and subsequent phases of the **Multi-Agent Legacy Code Modernization Platform** ("Rebase").

### Classification Tags
- **`SOURCE_REQUIREMENT`**: Explicit requirement originating from the platform TDD, architecture brief, or user request.
- **`PROPOSED_IMPLEMENTATION`**: Specific architectural, schema, or scaffolding design proposed to satisfy a source requirement.
- **`OPEN_DECISION`**: Decision requiring stakeholder confirmation or architectural consensus before Phase 1.
- **`OUT_OF_SCOPE`**: Capability explicitly excluded from V1 or deferred to future roadmap phases.

---

## 2. Requirements Traceability Matrix

| Requirement ID | Requirement Description | Classification | Source Reference | Responsible Component | Target Phase | Verification Method | Status |
| :--- | :--- | :--- | :--- | :--- | :---: | :--- | :---: |
| **REQ-PH0-001** | Inspect repository and produce initial gap analysis. | `SOURCE_REQUIREMENT` | Master Prompt §1 | Documentation | Phase 0 | Manual review of `docs/phase-0/gap-analysis.md` | **Verified** |
| **REQ-PH0-002** | Define V1 scope and supported stack pair. | `SOURCE_REQUIREMENT` | Master Prompt §5 | Architecture | Phase 0 | Document review in `docs/phase-0/v1-scope.md` | **Defined** |
| **REQ-PH0-003** | Select Java/Spring Boot → TypeScript/NestJS as default V1 slice. | `OPEN_DECISION` | Master Prompt §5 | Architecture | Phase 0 | Documented as proposal awaiting user approval | **Defined** |
| **REQ-PH0-004** | Document system architecture and 18 core component responsibilities. | `SOURCE_REQUIREMENT` | Master Prompt §6 | Architecture | Phase 0 | Review of `docs/phase-0/system-architecture.md` | **Defined** |
| **REQ-PH0-005** | Formulate outer-loop (Supervisor) and inner-loop (Agent) separation. | `SOURCE_REQUIREMENT` | Master Prompt §6 | Multi-Agent Core | Phase 0 | Mermaid flowcharts & contract specification | **Defined** |
| **REQ-PH0-006** | Define 13 domain entities, foreign keys, relationships, and ER diagram. | `SOURCE_REQUIREMENT` | Master Prompt §7 | Backend / Domain | Phase 0 | Pydantic schema validation & domain unit tests | **Implemented** |
| **REQ-PH0-007** | Define complete job lifecycle state machine and illegal transition checks. | `SOURCE_REQUIREMENT` | Master Prompt §8 | Backend / Domain | Phase 0 | Unit tests in `backend/tests/domain/` | **Implemented** |
| **REQ-PH0-008** | Define human approval gates G1, G2, G3, G4 with non-bypassable rules. | `SOURCE_REQUIREMENT` | Master Prompt §9 | Gate Service | Phase 0 | Security policy unit tests | **Implemented** |
| **REQ-PH0-009** | Prevent agents from self-approving gates. | `SOURCE_REQUIREMENT` | Master Prompt §9 | Security / Gate | Phase 0 | Authorization policy test | **Implemented** |
| **REQ-PH0-010** | Document authentication strategy (ADR) and RBAC permission matrix. | `SOURCE_REQUIREMENT` | Master Prompt §10 | AuthN / AuthZ | Phase 0 | Review of `authentication-authorization.md` | **Defined** |
| **REQ-PH0-011** | Minimum auth contracts: `POST /login`, `POST /logout`, `GET /me`. | `SOURCE_REQUIREMENT` | Master Prompt §10 | Backend API | Phase 0 | OpenAPI schema & API contract test | **Implemented** |
| **REQ-PH0-012** | Versioned API contracts under `/api/v1` namespace with error envelopes. | `SOURCE_REQUIREMENT` | Master Prompt §11 | Backend API | Phase 0 | FastAPI schema generation & contract tests | **Implemented** |
| **REQ-PH0-013** | Security threat model for untrusted repositories and sandboxes. | `SOURCE_REQUIREMENT` | Master Prompt §12 | Security | Phase 0 | Review of `security-threat-model.md` | **Defined** |
| **REQ-PH0-014** | Agent contracts, tool permission boundaries, token budgets, and timeouts. | `SOURCE_REQUIREMENT` | Master Prompt §13 | Multi-Agent Core | Phase 0 | Pydantic agent models & contract tests | **Implemented** |
| **REQ-PH0-015** | Implement 7 architecture, authentication, and workflow flowcharts. | `SOURCE_REQUIREMENT` | Master Prompt §15 | Architecture | Phase 0 | Mermaid diagram compilation in `flowcharts.md` | **Defined** |
| **REQ-PH0-016** | TDD backend executable scaffolding verifying Phase 0 contracts. | `SOURCE_REQUIREMENT` | Master Prompt §16 | Backend | Phase 0 | Pytest test run (`pytest backend/tests/`) | **Implemented** |
| **REQ-PH0-017** | Inspect existing UI reference folder `legacy-modernization-ui`. | `SOURCE_REQUIREMENT` | Master Prompt §14 | Frontend | Phase 0 | Verification of `ui-reference-assessment.md` | **Verified** |
| **REQ-PH0-018** | Map 15 core modernization concepts in the platform frontend. | `SOURCE_REQUIREMENT` | Master Prompt §14 | Frontend | Phase 0 | UI screen inspection & test build | **Verified** |
| **REQ-PH0-019** | Align frontend `api.ts` contracts with backend `/api/v1` Pydantic schemas. | `PROPOSED_IMPLEMENTATION`| Master Prompt §14 | Frontend / API | Phase 0 | Type inspection & compilation | **Implemented** |
| **REQ-PH0-020** | Execute frontend test suite and production build. | `SOURCE_REQUIREMENT` | Master Prompt §16 | Frontend / QA | Phase 0 | `npm test` and `npm run build` execution | **Verified** |
| **REQ-PH0-021** | Create comprehensive Phase 0 completion report. | `SOURCE_REQUIREMENT` | Master Prompt §19 | Documentation | Phase 0 | Review of `docs/phase-0/completion-report.md` | **Defined** |
| **REQ-FUT-001** | Production PostgreSQL migrations and database persistence. | `SOURCE_REQUIREMENT` | Phase 1 Master Prompt §4 | Database / Infra | Phase 1 | Alembic migrations (5a006735f454, e61a248e1494) & `tests/test_database.py` | **Implemented** |
| **REQ-FUT-002** | Live Git repository intake and controlled module branch adapter. | `SOURCE_REQUIREMENT` | Phase 1 Master Prompt §10 | Git Adapter | Phase 1 | `tests/test_phase1_git_adapter.py` (SSRF, clone, branch, diff) | **Implemented** |
| **REQ-PH1-001** | Server-side session authentication with HttpOnly cookies & bcrypt. | `SOURCE_REQUIREMENT` | Phase 1 Master Prompt §5 | AuthN / Backend | Phase 1 | `tests/test_phase1_auth.py` (login, rotation, invalidation, me) | **Implemented** |
| **REQ-PH1-002** | Resource-level JobMembership isolation & IDOR prevention. | `SOURCE_REQUIREMENT` | Phase 1 Master Prompt §6 | AuthZ / Security | Phase 1 | `tests/test_phase1_authorization.py` (non-member 404, role limits) | **Implemented** |
| **REQ-PH1-003** | Transactional job creation with owner membership & initial audit. | `SOURCE_REQUIREMENT` | Phase 1 Master Prompt §7 | Job Engine / DB | Phase 1 | `tests/test_phase1_jobs_and_audit.py` (atomic commit, cancel) | **Implemented** |
| **REQ-PH1-004** | Cryptographic artifact versioning, raw byte SHA-256 & lineage DAG. | `SOURCE_REQUIREMENT` | Phase 1 Master Prompt §8 | Artifacts / Storage | Phase 1 | `tests/test_phase1_artifacts_and_storage.py` (immutability, hash) | **Implemented** |
| **REQ-PH1-005** | Provider-independent object storage abstraction & staged writes. | `SOURCE_REQUIREMENT` | Phase 1 Master Prompt §9 | Storage / Core | Phase 1 | `tests/test_phase1_artifacts_and_storage.py` (roundtrip, escape) | **Implemented** |
| **REQ-PH1-006** | Append-only audit trail with service-level update/delete block. | `SOURCE_REQUIREMENT` | Phase 1 Master Prompt §11 | Audit / Governance | Phase 1 | `tests/test_phase1_jobs_and_audit.py` (Forbidden on mutation) | **Implemented** |
| **REQ-PH1-007** | Frontend integration with live session, credentials & permissions. | `SOURCE_REQUIREMENT` | Phase 1 Master Prompt §12 | Frontend / Client | Phase 1 | `frontend/src/tests/contracts.test.ts` & production build | **Implemented** |
| **REQ-FUT-003** | LangGraph multi-agent execution and LLM tool loops. | `OUT_OF_SCOPE` | Master Prompt §2 | Multi-Agent Core | Phase 2 | Mock model agent replay tests | Deferred |
| **REQ-FUT-004** | Containerized sandbox execution engine (Docker/gVisor). | `OUT_OF_SCOPE` | Master Prompt §12 | Infrastructure | Phase 2 | Sandbox isolation benchmarks | Deferred |
