# Human Approval Gate Policy: Multi-Agent Legacy Code Modernization Platform

**Document:** `docs/phase-0/gate-policy.md`  
**Phase:** Phase 0 (Discovery, Governance & Human-in-the-Loop Architecture)  
**Date:** October 19, 2026  
**Status:** Completed  
**Author:** Principal Software Architect & Security Lead  

---

## 1. Governance Principles & Strict Gate Invariants

Human-in-the-loop approval gates (G1 through G4) represent the central governance mechanism of the **Multi-Agent Legacy Code Modernization Platform** ("Rebase").

### Immutable Gate Invariants
1. **No Autonomous Self-Approval:** Under no circumstance may an AI agent, background worker, supervisor node, or automated test runner approve any gate. Every decision record requires an authenticated human user ID possessing the `REVIEWER` or `ADMIN` role.
2. **Blocking Workflow Semantics:** Workflow execution halts completely when entering an approval gate. No downstream tasks are scheduled, no conversion code is written, and no cloud budgets are consumed while a gate is pending.
3. **Mandatory Review Rationale:** An approval or rejection submitted without a non-empty written rationale (minimum 10 characters) is rejected with an HTTP 422 Unprocessable Entity error.
4. **Non-Bypassable Database Constraints:** State transitions out of gate states require a verified foreign key pointing to an immutable `gate_decision` row.

---

## 2. Gate Specification Matrix (G1–G4)

### 2.1 Gate G1 — Target Stack Feasibility Decision
- **Objective:** Evaluate legacy capability coverage against the target technology stack before dedicating resources to test capture and conversion.
- **Trigger Condition:** Legacy Analyzer and Feasibility agents complete dependency mapping and generate `FeasibilityReport v1`.
- **Required Evidence:**
  - `RepoInventory v1` (Language breakdown, entry points, LOC).
  - `FeasibilityReport v1` (Catalog of native, library-supported, and unsupported capabilities).
  - Identified capability gaps and suggested adapters (e.g., SOAP to REST wrapper, JasperReports to pdf-lib).
- **Authorized Roles:** `REVIEWER`, `ADMIN`, `SUPER_ADMIN`.
- **Allowed Decisions:** `APPROVED`, `REJECTED`.
- **Resolution Options Required:** For every identified capability gap, the reviewer must select:
  1. *Approve adapter* (e.g. use third-party library or micro-proxy).
  2. *Build custom adapter* (agent will synthesize custom translation layer).
  3. *Descope* (exclude capability from target service).
- **Rejection Behavior:** Workflow transitions to `FAILED` or returns to `ANALYZING` if the reviewer requests re-analysis with modified constraints.
- **Audit Logging:** Emits `GATE_G1_DECIDED` audit event with gap resolution choices and rationale.

### 2.2 Gate G2 — Characterization Suite Freeze
- **Objective:** Establish the immutable behavioral baseline representing the legacy system's contract before any code conversion begins.
- **Trigger Condition:** Characterizer agent captures legacy behavior across unit, API contract, and data layers, generating `CharacterizationSuite v1`.
- **Required Evidence:**
  - `CharacterizationSuite v1` with SHA-256 content hash.
  - Number of captured tests (e.g., 312 tests across 5 layers).
  - Legacy code coverage percentage (e.g., 84.2%).
  - Normalization rules (ID masks, timestamp tolerances, sorting orders).
- **Authorized Roles:** `REVIEWER`, `ADMIN`, `SUPER_ADMIN`.
- **Allowed Decisions:** `APPROVED`, `REJECTED`.
- **Approval Effect:** The suite's SHA-256 hash is permanently locked (`is_frozen = true`). CodeWriter agents in downstream stages are cryptographically restricted to read-only access to this suite.
- **Rejection Behavior:** Workflow returns to `CHARACTERIZING` with reviewer guidance to capture missing edge cases or correct flawed normalization rules.
- **Audit Logging:** Emits `GATE_G2_FROZEN` recording test count, suite hash, and reviewer rationale.

### 2.3 Gate G3 — Target Architecture & Conversion Plan Approval
- **Objective:** Approve the modular decomposition, dependency graph, conversion sequence (waves), and budget estimate.
- **Trigger Condition:** Architect and Planner agents produce `TargetBlueprint v2` and `ConversionPlan v3`.
- **Required Evidence:**
  - `TargetBlueprint v2` (NestJS modular architecture diagram, entity mappings, repository abstractions).
  - `ConversionPlan v3` (Module list, risk ratings [LOW, MEDIUM, HIGH], wave ordering DAG, estimated cost).
- **Authorized Roles:** `REVIEWER`, `ADMIN`, `SUPER_ADMIN`.
- **Allowed Decisions:** `APPROVED`, `REJECTED`.
- **Approval Effect:** Unlocks the `CONVERTING` stage. CodeWriter agents begin converting Wave 1 modules in parallel sandboxed Git branches.
- **Rejection Behavior:** Workflow returns to `PLANNING` with feedback (e.g. "Separate authentication from customer profile before starting Wave 1").
- **Audit Logging:** Emits `GATE_G3_DECIDED` with approved wave structure and reviewer signature.

### 2.4 Gate G4 — Final Equivalence & Delivery Approval
- **Objective:** Verify modernized codebase behavioral equivalence against the frozen characterization suite and authorize delivery pull request merge.
- **Trigger Condition:** All modules complete conversion; Verifier and Integrator agents generate `EquivalenceReport v2` and `JobReport v1`.
- **Required Evidence:**
  - `EquivalenceReport v2` (Passing tests count, equivalence percentage [e.g. 98.6%]).
  - List of classified behavioral differences (Regressions, Intended differences, Nondeterministic).
  - Uncovered legacy code risk assessment (branches not covered by tests).
  - Integration Git branch reference (`job/{id}/integration`) and draft PR.
- **Authorized Roles:** `REVIEWER`, `ADMIN`, `SUPER_ADMIN`.
- **Allowed Decisions:** `APPROVED`, `REJECTED`.
- **Waiver Requirement:** Any test classified as an *Intended Difference* requires an explicit signed waiver in the decision payload explaining why the behavioral deviation is acceptable (e.g. "Blocked negative stock inputs which legacy code mistakenly allowed").
- **Rejection Behavior:** Workflow returns to `CONVERTING` for repair attempts, or flags the job as `FAILED` if differences cannot be reconciled.
- **Approval Effect:** Job transitions to `COMPLETED`. Delivery PR is marked ready for production cutover review.
- **Audit Logging:** Emits `GATE_G4_APPROVED` recording all signed waivers, final equivalence score, and delivery authorization.

---

## 3. Idempotency & Resubmission Rules

1. **Idempotency:** A second submission of an identical decision for an active gate returns the existing decision record with HTTP 200 OK.
2. **Resubmission:** If a gate was previously `REJECTED` and the workflow looped back to re-analyze, re-characterize, or re-plan, a new gate instance is created with an incremented version (e.g. `G1-v2`). The historical rejected decision remains permanently immutable in `gate_decision`.
3. **Audit Trail Immutability:** Gate decisions cannot be modified or deleted once recorded.
