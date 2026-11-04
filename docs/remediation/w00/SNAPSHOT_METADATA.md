# W00 Baseline Snapshot & Environment Freeze Metadata

> **Audit Snapshot Date:** 2026-10-30  
> **Repository Baseline:** `main` at `3e69b506a3149509d791120ae785d0c1e4bed2a1`  
> **Integrity Guarantee:** Zero user modifications overwritten; working tree preserved.  

---

## 1. Version Control Baseline

### 1.1 Git Commit & Branch

```text
Commit SHA: 3e69b506a3149509d791120ae785d0c1e4bed2a1
Branch:     main (ahead of 'origin/main' by 1 commit)
Author:     Prior verified platform commit
```

### 1.2 Working Tree Status (`git status --porcelain`)

```text
 M .pytest_temp/test_repeated_failure_and_maxi0/authoritative_workspaces/job_0470dc0c-380e-4209-8e48-4593347c48f5
?? LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md
?? docs/audits/
?? docs/remediation/
?? backups/
?? tools/w00_*
```

*Verification:* No tracked code files in `backend/` or `frontend/` were modified. Baseline source files remain completely untouched.

---

## 2. Database Schema Revision

### 2.1 Current Alembic Migration Head

```bash
$ backend\.venv\Scripts\python.exe -m alembic -c backend\alembic.ini current
INFO  [alembic.runtime.migration] Context impl PostgresqlImpl.
INFO  [alembic.runtime.migration] Will assume transactional DDL.
d5e6f708192a (head)
```

- **Alembic Version in Live DB:** `d5e6f708192a`
- **Schema Drift Status (`alembic check`):** FAILED (drifts detected: unmapped `tasks` table, model vs index name differences, missing constraint definitions). Tracked as `DATA-02`.

---

## 3. Dependency Lockfiles & Cryptographic Checksums

| Dependency Artifact | Target Runtime | SHA-256 Checksum |
|---|---|---|
| `backend/requirements.txt` | Python 3.12 (FastAPI, SQLAlchemy, LangGraph) | `47251AE8918D78535FB8F5927A88BDD889792ECFCCA3183015002B803154FA37` |
| `frontend/package.json` | Node.js / React 18 / Vite 5 / Tailwind | `48F159E317F5566814364B7A2E2E325CF45599B2E323FEEC8E756A3B2FCEFA14` |
| `frontend/package-lock.json` | npm lockfile v3 | `81E45014C7595A4B834488407D28A0E10F17FC5A1ABA053F531D32BD702BA9D6` |

---

## 4. Container Images and Immutable Digests

| Image Repository | Tag | Image ID | Content Digest |
|---|---|---|---|
| `phase6-acceptance` | `local-v2` | `36add5930324` | `sha256:36add5930324d84c329adcc24f0f21622345a404adbf47197f1c5a9f3dc96001` |
| `phase7-acceptance` | `local-v1` | `545c07d7ed4b` | `sha256:545c07d7ed4b9858789a4c4fe9f8e642cbc2b932e721d9a597b8b07857ad722c` |
| `phase5-legacy-fixture` | `local-v1` | `c4b08a30ed93` | `sha256:c4b08a30ed93afecac971193131d4dadcbea7d112915749b7864a38676d481fb` |
| `phase6-acceptance` | `local-v1` | `78c7f2fa233e` | `sha256:78c7f2fa233ebfc26669a41e52154c62ede5b0d16b821dd83ca2dc5aeab9fac5` |
| `python` | `3.12-alpine` | `b658b05ce9c4` | `sha256:b658b05ce9c4eb97ec6fc19424818a1f31993659c2b505a532f470e83807815d` |
| `anchore/syft` | `latest` | `4cc92b64ca74` | `sha256:4cc92b64ca74ffca4c94d4c8fcc01f217731375300be14d0b6eeb2e82eaa110a` |
| `voice_assistance-backend` | `latest` | `0763bfc78d34` | `sha256:0763bfc78d34603462d6b6027ca68de4b1a4e7eb85007b6310add81002b4cb32` |
| `redis` | `7.4-alpine` | `ff02b58f971e` | `sha256:ff02b58f971e7d7d156a1267e283fcbbeee91773b6aa36c49dac28ecfe28eadf` |
| `pgvector/pgvector` | `pg16` | `ccc6e83d6e35` | `sha256:ccc6e83d6e35e931dc7c5def2022729d5a6c370318d099181995567ff1fb4d6b` |

---

## 5. Environment & Settings Snapshot (Secrets Redacted)

```ini
# Backend Service Configuration
ENVIRONMENT=development
DEBUG=true
PROJECT_NAME="Multi-Agent Legacy Code Modernization Platform API"
VERSION=1.0.0
API_V1_PREFIX=/api/v1
HOST=127.0.0.1
PORT=8000

# Security & Session Authentication
SECRET_KEY=[REDACTED_DEFAULT_INSECURE_DEV_KEY]
SESSION_COOKIE_NAME=rebase_session_id
SESSION_MAX_AGE_SECONDS=86400
SESSION_COOKIE_SECURE=false
SESSION_COOKIE_HTTPONLY=true
SESSION_COOKIE_SAMESITE=lax

# Frontend & Network Boundaries
CORS_ALLOWED_ORIGINS=http://localhost:3000,http://127.0.0.1:3000,http://localhost:8080,http://localhost:5173
ALLOWED_HOSTS=localhost,127.0.0.1,testserver
VITE_API_BASE_URL=/api/v1
VITE_PORT=3000

# Persistence & Storage
DATABASE_URL=postgresql+asyncpg://postgres:[REDACTED_DB_PASSWORD]@localhost:5432/rebase
REDIS_URL=redis://localhost:6379/0
ARTIFACT_STORAGE_PATH=./artifacts

# Multi-Agent LLM Model Keys
ANTHROPIC_API_KEY=[REDACTED]
OPENAI_API_KEY=sk-proj-[REDACTED_ACTIVE_TOKEN]
OPENROUTER_API_KEY=sk-or-v1-[REDACTED_ACTIVE_TOKEN]
DEFAULT_JOB_BUDGET_INR=15000.0
DEFAULT_JOB_BUDGET_USD=15000.0
MAX_REPAIR_ATTEMPTS=3
TOKEN_VELOCITY_LIMIT_PER_MINUTE=100000

# Container Sandboxing & Security Governance
SANDBOX_RUNTIME=gVisor-rootless
SANDBOX_NETWORK_EGRESS=air-gapped
ENFORCE_SECRET_REDACTION=true
MIN_RATIONALE_LENGTH=10

# Phase 7 Integration, SBOM & Sandbox Configuration
PHASE7_SANDBOX_IMAGE=sha256:545c07d7ed4b9858789a4c4fe9f8e642cbc2b932e721d9a597b8b07857ad722c
PHASE7_SBOM_TOOL=syft
PHASE7_PR_PROVIDER=
PHASE7_PR_BASE_BRANCH=main

# Phase 6 Scoped Conversion Sandbox
PHASE6_MODEL_PROVIDER=openai
PHASE6_MODEL_IDENTIFIER=gpt-4o-mini
PHASE6_SANDBOX_IMAGE=sha256:36add5930324d84c329adcc24f0f21622345a404adbf47197f1c5a9f3dc96001
PHASE6_TARGET_COMMAND_JSON=["python", "/adapter.py"]
```

---

## 6. Execution Freeze Verification

- **Backend Network Listeners:** Checked TCP port 8000. No listeners active.
- **Background Schedulers/Workers:** Checked active operating system processes. No Celery, RQ, or continuous pipeline daemons running.
- **Frontend Development Server:** Vite running on `localhost:3000` (read-only UI bundle; no standalone mutation capability without backend).
- **PostgreSQL Database:** Operating in read-only diagnostic mode for W00 verification.
- **Freeze Status:** **FROZEN & SIGNED OFF**.

