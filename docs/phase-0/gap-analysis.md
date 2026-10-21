# Phase 0 Initial Gap-Analysis Report: Multi-Agent Legacy Code Modernization Platform

**Document:** `docs/phase-0/gap-analysis.md`  
**Phase:** Phase 0 (Discovery, Architecture, Contracts & Foundation)  
**Date:** October 19, 2026  
**Status:** Completed  
**Author:** Principal Software Architect & QA Lead  

---

## 1. Investigation Overview & Baseline

This report documents the mandatory initial investigation of the repository [`rebase`](file:///c:/Users/EI%203/Desktop/rebase). The objective is to identify existing code, architectural decisions, technical debt, security gaps, and missing components prior to implementing Phase 0 architectural contracts and executable scaffolding.

### Classification Taxonomy
To ensure clarity and prevent premature implementation or false attribution:
- **`[SOURCE_REQUIREMENT]`**: Explicitly defined requirement from the platform specification or TDD.
- **`[PROPOSED_IMPLEMENTATION]`**: Recommended architectural design, pattern, or scaffolding fulfilling a source requirement.
- **`[OPEN_DECISION]`**: Underspecified requirement requiring explicit stakeholder or architectural sign-off.
- **`[OUT_OF_SCOPE]`**: Feature or technology explicitly excluded from Phase 0 or V1.

---

## 2. Existing Repository Inventory

### 2.1 File & Directory Structure
```text
rebase/
├── docs/
│   └── phase-0/
│       ├── ui-reference-assessment.md  (Completed UI reference assessment)
│       └── completion-report.md        (UI reference validation sign-off)
└── legacy-modernization-ui/            (Complete frontend application reference)
    ├── package.json                    (React 19, TanStack Start/Router/Query, Tailwind v4, Vite 8)
    ├── vite.config.ts                  (Nitro SSR + TanStack Start configuration)
    ├── src/
    │   ├── routes/                     (TanStack file-based routing: /, /jobs, /approvals, etc.)
    │   ├── components/
    │   │   ├── ui/                     (46 accessible Radix UI primitives)
    │   │   └── platform/               (Modernization domain components & interactive mock store)
    │   ├── pages/                      (Alternate REST prototype pages for /jobs, /reviews, etc.)
    │   ├── lib/api.ts                  (FastAPI client contract targeting http://localhost:8000/api/v1)
    │   └── styles.css                  (Tailwind v4 theme + custom OKLCH design tokens)
    └── src/test/                       (Vitest routing tests)
```

### 2.2 Existing Runtimes & Dependencies
1. **Frontend Runtime:**
   - Node.js v24.21.0 & npm 11.19.0.
   - React 19.2.0, `@tanstack/react-router` 1.170.41, `@tanstack/react-start` 1.168.60, Vite 8.1.5.
   - Tested and fully passing: `npm test` (Vitest) and `npm run build` (Vite client + Nitro server).
2. **Backend Runtime Available on Host:**
   - Python 3.13.9 / 3.14.0.
   - FastAPI 0.138.0, Pydantic 2.12.4, Uvicorn 0.49.0, Pytest 8.4.2, SQLAlchemy 2.0.43, PyJWT 2.10.1, HTTPX 0.28.1.
3. **Backend Codebase Status:**
   - **Currently Missing:** No `backend/` directory or FastAPI application exists in the repository. All backend contracts currently exist only as client expectations in [`src/lib/api.ts`](file:///c:/Users/EI%203/Desktop/rebase/legacy-modernization-ui/src/lib/api.ts) and mock state in [`src/components/platform/store.ts`](file:///c:/Users/EI%203/Desktop/rebase/legacy-modernization-ui/src/components/platform/store.ts).

---

## 3. Detailed Gap Analysis Matrix

| Requirement Area | Source Requirement `[SOURCE_REQUIREMENT]` | Existing State in Codebase | Gap Classification | Proposed Phase 0 Implementation `[PROPOSED_IMPLEMENTATION]` |
| :--- | :--- | :--- | :--- | :--- |
| **V1 Scope & Stack Pair** | Focus on single vertical slice stack pair; reject unsupported input. | UI provides options for Java/Spring, Python/Django, .NET, PHP; no strict backend validation. | `[OPEN_DECISION]` | Establish **Java 8–17 / Spring Boot → TypeScript / Node.js 22 / NestJS** as the primary V1 slice. Document in `docs/phase-0/v1-scope.md`. |
| **Backend API Scaffolding** | FastAPI application hosting versioned `/api/v1` routes with OpenAPI schema generation. | Non-existent. Only client fetch declarations in `api.ts`. | **MISSING** | Create minimal executable `backend/app/` with FastAPI app, Pydantic schemas, and routers. |
| **Authentication Design** | Mandatory auth strategy; minimum endpoints: `/auth/login`, `/auth/logout`, `/auth/me`. | UI has `/login` & `/signup` mockup and session-token paste field in Settings. No backend auth API. | **MISSING** | Select session-based cookie authentication with HttpOnly cookies & CSRF protection (ADR). Implement Pydantic auth contracts and routes. |
| **Role-Based Access Control** | Global and job-scoped roles (SUPER_ADMIN, ADMIN, DEVELOPER, REVIEWER, VIEWER). | Hardcoded string `Alex Morgan (Workspace admin)` in UI sidebar. | **MISSING** | Define domain RBAC model, permission matrix, and policy tests in Phase 0. |
| **Job Lifecycle State Machine** | Strict state machine with explicit preconditions, side effects, and terminal states. | UI lists states: `Running`, `Awaiting approval`, `Completed`, `Paused`, `Analyzing`. No transition validation. | **PARTIALLY IMPLEMENTED** | Implement formal state transition validator in `backend/app/domain/state_machine.py` with illegal transition rejection tests. |
| **Human Approval Gates (G1–G4)** | G1 (Feasibility), G2 (Characterization), G3 (Architecture/Plan), G4 (Delivery); human-only. | UI mocks review modals for G1 and G3 with written rationale requirement. | **PARTIALLY IMPLEMENTED** | Create formal gate policy specification, API schemas (`/jobs/{id}/gates/{gateId}/decisions`), and tests verifying agents cannot self-approve. |
| **Domain Model & Schemas** | 13 core entities (User, Role, Job, Artifact, Module, Attempt, AgentRun, TestCase, etc.). | UI defines partial client interfaces in `api.ts` and `data.ts`. | **PARTIALLY IMPLEMENTED** | Define full Pydantic domain models with foreign keys, constraints, retention policies, and Mermaid ER diagram. |
| **Security & Sandbox Threat Model** | Threat model covering untrusted repos, prompt injection, container escape, resource quotas. | UI notes "Isolate job execution in ephemeral sandboxes" as a mock toggle. | **MISSING** | Create comprehensive security threat model document covering trust boundaries, egress, and limits. |
| **Multi-Agent Contracts** | Outer loop (Supervisor) vs inner loop (Agents) contracts; token budgets, tools, timeouts. | UI displays 11 specialist agents and static execution traces. | **PARTIALLY IMPLEMENTED** | Specify typed agent input/output schemas, tool boundaries, and supervisor workflow contracts. |
| **Automated Contract Tests** | OpenAPI schema validation, domain state tests, security policy tests. | Only frontend route tests exist (`app-routing.test.tsx`). | **MISSING** | Implement Pytest contract test suite verifying OpenAPI schema, HTTP status codes, and error envelopes. |
| **Frontend Design System** | Modern light-theme design system, accessible contrast, responsive breakpoints, Lucide icons. | Implemented in `legacy-modernization-ui` using Tailwind v4, OKLCH, and Radix UI. | **IMPLEMENTED** | Preserve existing UI reference and align its `api.ts` client with backend schemas. |

---

## 4. Architectural Conflicts & Inconsistencies

1. **Dual Frontend Implementations:**
   - *Conflict:* The reference folder contains both a TanStack Start/Router app (`src/routes/` + `src/components/platform/`) and an older React Router DOM app (`src/pages/` + `src/components/Layout.tsx`).
   - *Resolution:* TanStack Start is the modern, type-safe architecture. The platform standardizes on `src/routes/` as the primary routing tree, while retaining `src/lib/api.ts` for unified backend REST calls.
2. **Client-Side Token Storage vs. Secure Session Cookies:**
   - *Conflict:* `src/lib/api.ts` and `src/pages/Settings.tsx` use manual Bearer token entry stored in `sessionStorage`.
   - *Resolution:* While acceptable as an interim preview mechanism, Phase 0 must document a secure server-side session architecture utilizing `HttpOnly`, `SameSite=Lax`, and `Secure` cookies for browser clients to prevent XSS exfiltration.
3. **Approval Gate Discovery:**
   - *Conflict:* `src/pages/Review.tsx` explicitly notes that the existing backend contract has an endpoint to submit a gate decision (`POST /jobs/{id}/gates/{gate_id}/decisions`), but lacks a query endpoint to list all pending gates across jobs.
   - *Resolution:* Add `GET /api/v1/gates/pending` and `GET /api/v1/jobs/{id}/gates` to the Phase 0 API contract specification.

---

## 5. Security Concerns Identified

1. **Untrusted Code Execution:** The platform processes legacy repositories which may contain obfuscated exploits, vulnerabilities, or malicious build scripts. Execution must never occur on the host system.
2. **Prompt Injection in Source Files:** Comments and string literals in legacy code can act as adversarial jailbreaks against model reasoning. Structured XML tagging and schema-constrained tool execution are required.
3. **Agent Self-Approval Risk:** Autonomous agents must be structurally prohibited from emitting gate approval tokens. Approval must require authenticated human session tokens with `REVIEWER` or `ADMIN` roles.
4. **Cross-Job Tenant Isolation:** Artifacts, test cases, and agent checkpoints must be strictly scoped by `job_id` and verified against user authorization to prevent cross-job data leakage.

---

## 6. Proposed Phase 0 Implementation Plan

1. **Documentation Deliverables:**
   - `docs/phase-0/gap-analysis.md` (This document)
   - `docs/phase-0/requirements-traceability.md`
   - `docs/phase-0/v1-scope.md`
   - `docs/phase-0/system-architecture.md`
   - `docs/phase-0/domain-model.md`
   - `docs/phase-0/job-state-machine.md`
   - `docs/phase-0/gate-policy.md`
   - `docs/phase-0/authentication-authorization.md`
   - `docs/phase-0/api-contracts.md`
   - `docs/phase-0/security-threat-model.md`
   - `docs/phase-0/agent-contracts.md`
   - `docs/phase-0/flowcharts.md`
2. **Executable Backend Foundation:**
   - Initialize `backend/` with FastAPI application exposing versioned `/api/v1` routes.
   - Define Pydantic request/response/error schemas matching contracts.
   - Implement domain state machine and gate policy validation logic.
   - Implement contract, domain, and authorization policy test suites in `backend/tests/`.
3. **Frontend Contract Alignment:**
   - Update `legacy-modernization-ui/src/lib/api.ts` to ensure 100% schema compatibility with backend Pydantic models.
   - Verify frontend tests (`vitest`) and production build (`vite build`).
4. **Phase 0 Completion & Acceptance:**
   - Compile comprehensive `docs/phase-0/completion-report.md` with test execution logs.

---

## 7. Risks & Open Decisions

- **`[OPEN_DECISION]` V1 Stack Pair:** Proposing Java/Spring Boot → Node.js/NestJS based on available AST tooling (Tree-sitter, JavaParser) and market demand. Awaiting final user approval.
- **`[OPEN_DECISION]` Identity Provider:** Recommend standard OAuth2/OIDC (Okta/Keycloak/GitHub) integration in Phase 1 while providing username/password session auth in local development.
- **`[RISK]` Non-Deterministic Model Output:** Mitigated by characterization test suites (G2) capturing golden legacy inputs/outputs before any code conversion begins.
