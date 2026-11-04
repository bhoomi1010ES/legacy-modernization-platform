# W02 — Isolated Reproducible Test Infrastructure and CI (P0)

> **Workstream:** `W02`  
> **Status:** **COMPLETED & SIGNED OFF**  
> **Sign-Off Date:** 2026-10-30  
> **Target Environment:** `ENV-LOCAL-DEV-POSTGRES18` / GitHub Actions CI  
> **Target Commits:** `3e69b506a3149509d791120ae785d0c1e4bed2a1`  
> **Lead Implementer:** Senior Application Security Engineer & Backend Architect  
> **Closed Ledger Findings:** `TEST-04`  

---

## 1. Executive Summary

Prior to W02, full test execution risked mutating the persistent development database (`localhost:5432/rebase`), spending real model provider funds, and touching unauthorized remote repositories (`TEST-04`).

Workstream **W02** establishes hermetic, reproducible, isolated test infrastructure and continuous integration pipelines without modifying existing production business architectures.

### Key Achievements
1. **Automated Disposable PostgreSQL Lifecycle**: Zero mutation of persistent data. Each test run dynamically provisions an unpredictable database (`rebase_test_<uuid>`), executes complete Alembic migrations (`alembic upgrade head`), and guarantees clean teardown via connection termination and force drop.
2. **Strict Production Resource Refusal Guard**: `IsolationGuard` actively refuses any test execution targeting `rebase`, `production`, `staging`, or databases lacking disposable markers (`ProtectedResourceError`), and verifies `TEST_ISOLATION_TOKEN`.
3. **Two Model Lanes Policy**:
   - **Lane 1 (Deterministic Fake)**: Mandatory for unit/CI tests. Zero cost, deterministic scripted responses, with responses strictly flagged as not eligible for real E2E acceptance claims.
   - **Lane 2 (Budget-Capped Real Sandbox)**: Explicitly disabled by default (`REAL_MODEL_SANDBOX_ENABLED=False`). Requires explicit opt-in, strict dollar budget ceilings (`MAX_BUDGET_USD`), and automatic halting on budget exhaustion.
4. **Committed Synthetic Reference Repositories**: 7 license-clear reference fixtures for conversion, static web characterization, SQL services, broken compilers, slow workers, and negative security testing.
5. **Standardized Pytest Markers & Machine-Readable Reporting**: Registered `unit`, `db_integration`, `sandbox_real`, `security_negative`, `e2e_fixture`, `e2e_real_model`, `chaos`, generating JUnit XML and coverage reports.
6. **Continuous Integration Automation**: Production-grade `.github/workflows/ci.yml` with pinned action SHAs, and a local multi-gate runner `tools/run_ci_checks.py`.

---

## 2. Architecture & Components Implemented

### 2.1 Isolation Guard & Disposable Database Manager
- **File:** [`backend/app/core/testing_infrastructure.py`](file:///c:/Users/lenovo/Desktop/rebase/backend/app/core/testing_infrastructure.py)
- **`IsolationGuard`**:
  - `extract_database_name(url)`: Robustly parses database names from async and sync PostgreSQL URLs.
  - `verify_database_url(url, token)`: Blocks `rebase`, `production`, `staging`, `rebase_db`, and verifies `TEST_ISOLATION_TOKEN`.
  - `verify_storage_path(path)`: Rejects persistent production storage roots; enforces temp directory boundaries.
  - `verify_git_remote(url)`: Rejects external production Git remotes during test execution; requires local fixture remotes.
- **`DisposableDatabaseManager`**:
  - `generate_database_name()`: Produces unpredictable names: `rebase_test_{uuid4().hex[:12]}`.
  - `generate_isolation_token()`: Issues cryptographic hex token into environment.
  - `create_database(db_name)`: Connects to administrative PostgreSQL instance with autocommit and provisions clean DB.
  - `run_migrations(db_name)`: Runs `alembic upgrade head` programmatically, seeding all 30+ tables.
  - `drop_database(db_name)`: Queries `pg_stat_activity`, terminates all open connections (`pg_terminate_backend(pid)`), and drops the database with `DROP DATABASE IF EXISTS ... WITH (FORCE)`.
  - `cleanup_all()`: Registered via `atexit` to guarantee teardown on normal or abnormal process exit.

### 2.2 Pytest Configuration & Test Fixtures
- **Config:** [`backend/pytest.ini`](file:///c:/Users/lenovo/Desktop/rebase/backend/pytest.ini)
  - Configured test paths, options `--basetemp=.pytest_temp -ra -v --junitxml=.test_runs/junit.xml -rsxX`.
  - Registered markers: `unit`, `db_integration`, `sandbox_real`, `security_negative`, `e2e_fixture`, `e2e_real_model`, `chaos`.
- **Fixtures:** [`backend/tests/conftest.py`](file:///c:/Users/lenovo/Desktop/rebase/backend/tests/conftest.py)
  - `test_isolation_token`: Active cryptographic token.
  - `client`: Thread-safe FastAPI test client.
  - `db_session`: Isolated async SQLAlchemy session.
  - `temp_artifact_storage`: Isolated temporary directory.
  - `reference_fixtures`: Access to synthetic repositories.
  - `deterministic_fake_gateway`: Pre-configured fake model gateway for zero-cost tests.
  - `disposable_postgres_db`: Disposable database fixture with guaranteed cleanup.

### 2.3 Two Model Lanes Architecture
- **File:** [`backend/app/services/model_gateway.py`](file:///c:/Users/lenovo/Desktop/rebase/backend/app/services/model_gateway.py)
- **`ModelLane`**:
  - `DETERMINISTIC_FAKE = "deterministic_fake"`:
    - Responses have `usage.cost_usd = 0.0`.
    - `provider_metadata["model_lane"] = "deterministic_fake"`.
    - `provider_metadata["acceptance_claim_valid"] = False`.
    - `provider_metadata["audit_note"] = "Deterministic fake provider; not eligible as real E2E acceptance evidence"`.
  - `BUDGET_CAPPED_REAL = "budget_capped_real"`:
    - Blocked unless `settings.REAL_MODEL_SANDBOX_ENABLED == True`.
    - `RealModelBudgetTracker` tracks cumulative dollar spend.
    - If cumulative spend exceeds `settings.MAX_BUDGET_USD`, raises `ModelGatewayError`.
    - `provider_metadata["acceptance_claim_valid"] = True`.
- **`TwoLaneModelRouter`**:
  - `get_lane_gateway(lane)`: Resolves appropriate gateway depending on required lane.

### 2.4 Committed Synthetic Reference Repositories
- **Directory:** [`backend/tests/fixtures/reference_repos/`](file:///c:/Users/lenovo/Desktop/rebase/backend/tests/fixtures/reference_repos/)
- **Loader:** [`backend/tests/fixtures/fixture_loader.py`](file:///c:/Users/lenovo/Desktop/rebase/backend/tests/fixtures/fixture_loader.py)
1. `fastapi_source`: Minimal FastAPI REST API with Pydantic inventory models and routes.
2. `django_target`: Modernized Django REST Framework ViewSet and serializer equivalent.
3. `static_web_app`: Semantic HTML5, CSS, and client-side JavaScript for characterization.
4. `sql_backed_service`: SQLAlchemy declarative relational models (`Customer`, `Order`) and database service.
5. `broken_fixture`: Intentional Python syntax error and missing import for compiler failure tests.
6. `slow_worker_fixture`: Controllable long-running execution loop for worker timeout and cancellation testing.
7. `malicious_security_fixture`: Path traversal (`/etc/shadow`, `SAM`), SSRF (`169.254.169.254`, `127.0.0.1`), and prompt-injection attack payloads.

### 2.5 CI Workflow & Local Pipeline Runner
- **CI Workflow:** [`.github/workflows/ci.yml`](file:///c:/Users/lenovo/Desktop/rebase/.github/workflows/ci.yml)
  - Pinned actions (`actions/checkout@11bd71901bbe5b1630ceea73d27597364c9af683`, `actions/setup-python@42375524e23c412d93fb67b49958b491fce71c38`, `actions/setup-node@1d0ff469b7ec7b3cb9d8673fde0c81c44821de2a`).
  - Read-only token permissions (`permissions: contents: read`).
  - Independent jobs: `lint-and-format`, `backend-security-and-isolation`, `disposable-db-integration`, `frontend-test-and-build`.
- **Local Runner:** [`tools/run_ci_checks.py`](file:///c:/Users/lenovo/Desktop/rebase/tools/run_ci_checks.py)
  - Runs Black format checking, production DB refusal guard, unit/security tests, disposable DB lifecycle, W01 security suite, frontend Vitest suite, and frontend Vite build.

---

## 3. Verification & Test Evidence

### 3.1 Test Suite Summary
| Test Target | Suite File | Total Tests | Passed | Failed | Duration |
|---|---|---|---|---|---|
| W02 Isolation & Infrastructure | `backend/tests/test_w02_isolation_and_ci.py` | 15 | 15 (100%) | 0 | 3.45s |
| W01 Security Regression | `backend/tests/test_w01_security.py` | 19 | 19 (100%) | 0 | 12.86s |
| Frontend Vitest Unit Tests | `frontend/src/tests/*.test.ts(x)` | 43 | 43 (100%) | 0 | 2.97s |
| Frontend Production Build | `frontend/dist/` (tsc + vite) | 1 build | 1 (100%) | 0 | 9.58s |

### 3.2 Specific Test Cases Verified
- `test_production_database_url_refusal`: **PASSED**. Confirmed refusal of `localhost:5432/rebase`, `production`, `staging`, etc.
- `test_unmarked_database_url_refusal`: **PASSED**. Confirmed refusal of unmarked databases without test/disposable tags.
- `test_valid_disposable_database_url_allowed`: **PASSED**. Confirmed permitted access for `rebase_test_*`.
- `test_isolation_token_enforcement`: **PASSED**. Confirmed rejection when `TEST_ISOLATION_TOKEN` is mismatched.
- `test_storage_path_isolation`: **PASSED**. Confirmed rejection of persistent storage roots.
- `test_git_remote_isolation`: **PASSED**. Confirmed rejection of external production Git repositories.
- `test_disposable_postgres_lifecycle`: **PASSED**. Confirmed programmatic database creation, Alembic migration of 30+ tables, catalog verification, and complete force-drop cleanup.
- `test_deterministic_fake_model_lane`: **PASSED**. Confirmed zero cost and invalid acceptance claim metadata flag.
- `test_real_model_lane_disabled_by_default`: **PASSED**. Confirmed `ModelNotAllowedError` when `REAL_MODEL_SANDBOX_ENABLED=False`.
- `test_real_model_lane_budget_cap_enforcement`: **PASSED**. Confirmed spend tracking and hard stop at `$0.05` budget ceiling.
- `test_synthetic_reference_fixtures_integrity`: **PASSED**. Confirmed presence and validity of all 7 reference fixtures.
- `test_empty_database_url_refusal`: **PASSED**. Confirmed error on empty URL.
- `test_invalid_database_name_pattern`: **PASSED**. Confirmed error on SQL injection in DB name.
- `test_two_lane_router_dispatch`: **PASSED**. Confirmed gateway resolution across lanes.
- `test_disposable_db_manager_cleanup_all`: **PASSED**. Confirmed safe batch teardown.

---

## 4. Ledger Status & Sign-Off

- **Remediation Evidence Ledger:** [`docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md`](file:///c:/Users/lenovo/Desktop/rebase/docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md)
  - `TEST-04`: Marked **`FIXED`** with comprehensive reproduction and verification evidence.
- **Implementation Plan:** [`LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md`](file:///c:/Users/lenovo/Desktop/rebase/LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md)
  - Section 5 (W02): Marked **`COMPLETED & SIGNED OFF`**.

**Conclusion:** All W02 objectives have been implemented and verified. The platform now operates with complete test isolation, zero risk to persistent data, and deterministic CI execution.

