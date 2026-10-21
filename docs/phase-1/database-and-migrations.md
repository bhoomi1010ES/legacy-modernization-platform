# Database Architecture, Models & Migrations
## Phase 1 Persistence Specification

**Document:** `docs/phase-1/database-and-migrations.md`  
**Phase:** Phase 1 (Database & Persistence Engine)  
**Date:** October 19, 2026  
**Status:** Completed & Verified  

---

## 1. PostgreSQL Architecture & Connection Lifecycle

The platform uses **SQLAlchemy 2.x async ORM** backed by native **asyncpg** for high-throughput, non-blocking PostgreSQL connectivity.

### Host and Connection Configuration
- **Active Engine:** PostgreSQL 18.4 on Windows x86_64
- **Host Port:** `localhost:5433` (configured via `DATABASE_URL` in `.env`)
- **Connection URI:** `postgresql+asyncpg://postgres:postgres123@localhost:5433/rebase_db`
- **Native Async Driver:** `asyncpg` for direct health ping probes and connection pooling.
- **ORM Session Factory:** `async_sessionmaker(bind=engine, class_=AsyncSession, expire_on_commit=False)`
- **Test Isolation:** Automatic `NullPool` allocation under `ENVIRONMENT=testing` to eliminate connection reuse across disparate anyio event loops.

---

## 2. Relational Schema & 15 Migrated Tables

The database schema mirrors the Phase 0 Domain Model and adds session management and migration tracking:

| Table Name | Primary Key | Foreign Keys | Key Constraints & Indexes |
| :--- | :--- | :--- | :--- |
| **`roles`** | `role_id VARCHAR(50)` | None | PK `role_id`, Unique `name`. |
| **`users`** | `user_id UUID` | None | Unique Index `ix_users_email`, Check `status IN ('ACTIVE', 'INACTIVE', 'SUSPENDED')`. |
| **`user_sessions`** | `session_id VARCHAR(128)` | `user_id -> users.user_id` (CASCADE) | Index `ix_user_sessions_active (user_id, is_revoked, expires_at)`, Index `token_hash`. |
| **`jobs`** | `job_id UUID` | `owner_user_id -> users.user_id` | Check `status IN (...)`, Index `ix_jobs_owner_status`, Index `ix_jobs_created_at_desc`. |
| **`job_memberships`**| `membership_id UUID` | `job_id -> jobs.job_id`, `user_id -> users.user_id`, `role_id -> roles.role_id` | Unique `uq_user_job_membership (user_id, job_id)`, Index `(user_id, role_id)`. |
| **`artifacts`** | `artifact_id UUID` | `job_id -> jobs.job_id`, `module_id -> modules.module_id` | Unique `uq_artifact_version (job_id, artifact_type, version)`, Index `content_hash`. |
| **`modules`** | `module_id UUID` | `job_id -> jobs.job_id` | Check `risk_level IN ('LOW', 'MEDIUM', 'HIGH')`, Index `(job_id, status)`. |
| **`module_attempts`**| `attempt_id UUID` | `module_id -> modules.module_id`, `agent_run_id -> agent_runs.run_id` | Unique `(module_id, attempt_number)`, Check `attempt_number <= 5`. |
| **`agent_runs`** | `run_id UUID` | `job_id -> jobs.job_id` | Index `ix_agent_runs_job_agent (job_id, agent_name, started_at)`. |
| **`test_cases`** | `test_case_id UUID` | `job_id -> jobs.job_id`, `module_id -> modules.module_id` | Check `test_layer IN ('UNIT', 'API_CONTRACT', ...)`, Index `(job_id, test_layer)`. |
| **`test_results`** | `result_id UUID` | `test_case_id -> test_cases.test_case_id`, `attempt_id -> module_attempts.attempt_id` | Check `outcome IN ('PASSED', 'FAILED')`, Check `difference_classification IN (...)`. |
| **`gate_decisions`** | `decision_id UUID` | `job_id -> jobs.job_id`, `reviewer_user_id -> users.user_id` | Check `gate_type IN ('G1', 'G2', 'G3', 'G4')`, Check `decision IN ('APPROVED', 'REJECTED')`. |
| **`audit_events`** | `event_id UUID` | `job_id -> jobs.job_id` | Check `actor_type IN ('USER', 'SYSTEM', 'AGENT')`, Index `(job_id, created_at)`. |
| **`budget_usage`** | `usage_id UUID` | `job_id -> jobs.job_id`, `run_id -> agent_runs.run_id` | Index `ix_budget_usage_job_recorded (job_id, recorded_at)`. |
| **`alembic_version`**| `version_num VARCHAR(32)` | None | Alembic migration state tracking. |

---

## 3. Alembic Migration History

Migrations are forward-only and managed in `backend/alembic/versions/`:

1. **`5a006735f454_initial_phase1_schema.py`**:
   - Creates all initial 14 domain tables, primary keys, foreign key constraints with cascading rules, check constraints, and performance indexes.
2. **`e61a248e1494_widen_artifact_content_hash.py`**:
   - Expands `artifacts.content_hash` from `VARCHAR(64)` to `VARCHAR(128)` to safely support both raw 64-char hex strings and prefixed `sha256:...` checksum notations.

### Reproducible Setup Commands

```bash
# 1. Verify PostgreSQL service is active
python scripts/check_db.py

# 2. Run forward migrations
alembic upgrade head

# 3. Seed standard RBAC roles (SUPER_ADMIN, ADMIN, REVIEWER, DEVELOPER, VIEWER)
python scripts/seed_roles.py

# 4. Bootstrap initial administrator account
python scripts/create_admin.py --email "alex.morgan@acme.corp" --password "SecurePassword123!"

# 5. Seed baseline demo jobs
python scripts/seed_demo_jobs.py
```
