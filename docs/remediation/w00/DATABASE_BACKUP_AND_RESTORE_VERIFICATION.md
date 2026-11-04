# W00 Database Backup & Isolated Restore Verification Report

> **Program:** Legacy Modernization Platform Remediation  
> **Phase:** W00 — Freeze, preserve, verify the audit  
> **Date:** 2026-10-30  
> **Status:** **VERIFIED & SIGNED-OFF**  
> **Source Host:** PostgreSQL 18.0 (Windows x64 on `localhost:5432`)  
> **Source Database:** `rebase`  
> **Target Disposable DB:** `rebase_disposable_w00_verify`  

---

## 1. Executive Summary

As mandated by **W00 Step 3** of the Remediation Implementation Plan, a full physical and logical snapshot of the persistent PostgreSQL development database `rebase` was created before any code or schema remediation was initiated.

The backup was subsequently restored into an isolated, disposable database (`rebase_disposable_w00_verify`) within the local PostgreSQL instance. A table-by-table schema and row-count verification script (`tools/w00_verify_restore.py`) proved a **100% exact match** across all **36 tables** and all **279,432 rows**. No external network calls or production endpoints were contacted during this procedure. Following successful verification, the disposable database was safely dropped.

---

## 2. Backup Execution & Cryptographic Manifest

### 2.1 Backup Generation Commands

```powershell
$env:PGPASSWORD="postres123"

# 1. Custom binary archive format (supports pg_restore, compression, and selective restore)
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" `
    --host=localhost `
    --port=5432 `
    --username=postgres `
    --dbname=rebase `
    --format=custom `
    --file="backups/rebase_w00_freeze_20261030.dump"

# 2. Plain SQL text script format (for human inspection, diffing, and universal SQL replay)
& "C:\Program Files\PostgreSQL\18\bin\pg_dump.exe" `
    --host=localhost `
    --port=5432 `
    --username=postgres `
    --dbname=rebase `
    --format=plain `
    --file="backups/rebase_w00_freeze_20261030.sql"

Remove-Item Env:\PGPASSWORD
```

### 2.2 Backup Artifacts & SHA-256 Hashes

| File | Format | File Size | SHA-256 Checksum |
|---|---|---:|---|
| `backups/rebase_w00_freeze_20261030.dump` | PostgreSQL Custom (`-Fc`) | 26,527,565 bytes (25.3 MB) | `40F40911F9275B22D9810C3B86A7D89456FD646BE82F72EB4C5F77BCFE3A4AC1` |
| `backups/rebase_w00_freeze_20261030.sql` | SQL Text (`-Fp`) | 187,198,448 bytes (178.5 MB) | `94443F251DFEC107EB3B344EA9B94673A2775F19E90CE3E0D6CD390A7AF60F1A` |

---

## 3. Isolated Disposable Environment Restoration

### 3.1 Provisioning and Restore Commands

```powershell
$env:PGPASSWORD="postres123"
$disposableDb = "rebase_disposable_w00_verify"

# 1. Ensure clean slate
& "C:\Program Files\PostgreSQL\18\bin\dropdb.exe" --host=localhost --port=5432 --username=postgres --if-exists $disposableDb

# 2. Create isolated disposable database
& "C:\Program Files\PostgreSQL\18\bin\createdb.exe" --host=localhost --port=5432 --username=postgres $disposableDb

# 3. Restore custom dump into disposable database
& "C:\Program Files\PostgreSQL\18\bin\pg_restore.exe" --host=localhost --port=5432 --username=postgres --dbname=$disposableDb "backups/rebase_w00_freeze_20261030.dump"

Remove-Item Env:\PGPASSWORD
```

Restore execution finished cleanly with exit code `0`.

---

## 4. 1:1 Schema and Data Equivalence Verification

Verification was executed via automated Python script (`tools/w00_verify_restore.py`), connecting asynchronously to both `rebase` and `rebase_disposable_w00_verify` simultaneously.

### 4.1 Global Metrics

- **Original Public Tables:** 36
- **Restored Public Tables:** 36
- **Schema Match:** 100% Identical
- **Original Total Rows:** 279,432
- **Restored Total Rows:** 279,432
- **Data Match:** 100% Identical (0 mismatches)

### 4.2 Comprehensive Table-by-Table Row Count Audit

| # | Table Name | Original Database (`rebase`) | Disposable Restored Database | Match Status |
|---|---|---:|---:|:---:|
| 1 | `agent_runs` | 1,006 | 1,006 | **PASS** |
| 2 | `alembic_version` | 1 | 1 | **PASS** |
| 3 | `analysis_conflicts` | 0 | 0 | **PASS** |
| 4 | `analysis_evidence` | 1,181 | 1,181 | **PASS** |
| 5 | `analysis_runs` | 43 | 43 | **PASS** |
| 6 | `analysis_workers` | 344 | 344 | **PASS** |
| 7 | `artifacts` | 2,337 | 2,337 | **PASS** |
| 8 | `audit_events` | 70,692 | 70,692 | **PASS** |
| 9 | `budget_usage` | 581 | 581 | **PASS** |
| 10 | `conversion_plan_dependencies` | 78 | 78 | **PASS** |
| 11 | `conversion_plan_modules` | 151 | 151 | **PASS** |
| 12 | `conversion_plan_tasks` | 401 | 401 | **PASS** |
| 13 | `conversion_plans` | 32 | 32 | **PASS** |
| 14 | `feasibility_capabilities` | 544 | 544 | **PASS** |
| 15 | `feasibility_decisions` | 0 | 0 | **PASS** |
| 16 | `feasibility_reports` | 43 | 43 | **PASS** |
| 17 | `gate_decisions` | 739 | 739 | **PASS** |
| 18 | `job_memberships` | 905 | 905 | **PASS** |
| 19 | `jobs` | 2,518 | 2,518 | **PASS** |
| 20 | `legacy_models` | 72 | 72 | **PASS** |
| 21 | `module_attempts` | 318 | 318 | **PASS** |
| 22 | `modules` | 1,007 | 1,007 | **PASS** |
| 23 | `planner_outputs` | 151 | 151 | **PASS** |
| 24 | `planner_runs` | 32 | 32 | **PASS** |
| 25 | `repository_inventories` | 65 | 65 | **PASS** |
| 26 | `repository_snapshots` | 94 | 94 | **PASS** |
| 27 | `roles` | 5 | 5 | **PASS** |
| 28 | `target_blueprints` | 72 | 72 | **PASS** |
| 29 | `tasks` | 34 | 34 | **PASS** |
| 30 | `test_cases` | 695 | 695 | **PASS** |
| 31 | `test_results` | 2,302 | 2,302 | **PASS** |
| 32 | `user_sessions` | 1,053 | 1,053 | **PASS** |
| 33 | `users` | 184 | 184 | **PASS** |
| 34 | `workflow_checkpoints` | 158,335 | 158,335 | **PASS** |
| 35 | `workflow_gates` | 2,118 | 2,118 | **PASS** |
| 36 | `workflow_outbox` | 31,299 | 31,299 | **PASS** |
| **TOTAL** | **36 Tables** | **279,432** | **279,432** | **100% IDENTICAL** |

---

## 5. Teardown and Cleanup

After verification of the table schemas and row counts, the disposable database was cleanly destroyed:

```powershell
$env:PGPASSWORD="postres123"
& "C:\Program Files\PostgreSQL\18\bin\dropdb.exe" --host=localhost --port=5432 --username=postgres "rebase_disposable_w00_verify"
Remove-Item Env:\PGPASSWORD
```

Confirmation was checked: `rebase_disposable_w00_verify` no longer exists on the database server. Persistent data remains untouched and fully protected.

