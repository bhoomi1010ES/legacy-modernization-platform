# Operational Runbook: Database Failover, Backup & Migration Alignment

> **Audience:** Database Administrators (DBA), SRE, Infrastructure Leads  
> **Classification:** Production Operational Runbook (Phase 8)  
> **Last Verified:** 2026-11-05  

---

## 1. Scope & Objective

This runbook outlines standard operating procedures for executing database failover, point-in-time recovery (PITR), schema migration rollbacks, and replica promotion for the primary PostgreSQL cluster.

---

## 2. Recovery Time & Point Objectives (RTO / RPO)

- **Recovery Time Objective (RTO):** < 15 minutes to fully restored read/write capability.
- **Recovery Point Objective (RPO):** < 5 minutes of data loss under automated WAL archiving.
- **Data Integrity SLA:** 100% schema and cryptographic checksum equivalence across all 46 tables.

---

## 3. High-Availability Architecture

```
                 +-----------------------+
                 |    FastAPI Backend    |
                 +-----------+-----------+
                             |
                   DATABASE_URL (PgBouncer)
                             |
              +--------------+--------------+
              |                             |
     (Primary - Read/Write)         (Standby - Streaming Replica)
     PostgreSQL Node 1              PostgreSQL Node 2
              |                             ^
              +======= WAL Streaming =======+
```

---

## 4. Failover & Recovery Procedures

### SOP-DB-01: Primary Node Failover & Replica Promotion

#### Trigger
- Primary PostgreSQL instance unreachable (TCP connection timeout > 10s, hardware crash, disk corruption).

#### Procedure
1. **Fence Failed Primary (Stonith / Isolation):**
   - Cut network egress to failed Primary Node 1 to prevent split-brain writes.
2. **Promote Standby Replica to Primary:**
   ```bash
   pg_ctl promote -D /var/lib/postgresql/data
   ```
3. **Verify Read/Write State on Promoted Node:**
   ```sql
   SELECT pg_is_in_recovery(); -- Must return FALSE
   CREATE TEMP TABLE failover_probe (id int);
   DROP TABLE failover_probe;
   ```
4. **Repoint PgBouncer / Application Connection Pool:**
   - Update DNS record `db.internal.rebase` or PgBouncer backend target to Node 2 IP.
   - Reload PgBouncer:
     ```bash
     pg_bouncer -R /etc/pgbouncer/pgbouncer.ini
     ```
5. **Drain and Reset Backend Connection Pools:**
   - FastAPI AsyncEngine automatically discards broken asyncpg connections on reconnect.

---

### SOP-DB-02: Point-in-Time Restore from Backup Dump

#### Trigger
- Accidental catastrophic data corruption or unrecoverable schema error.

#### Procedure
1. **Stop Application Backend:**
   ```bash
   systemctl stop rebase-backend.service
   ```
2. **Verify Backup Dump Integrity:**
   ```powershell
   $sha = Get-FileHash -Algorithm SHA256 "backups/rebase_phase8_prod_ready_20261105.dump"
   Write-Host "Dump SHA-256: $($sha.Hash)"
   ```
3. **Drop and Recreate Clean Database:**
   ```powershell
   dropdb --host=localhost --port=5432 --username=postgres --if-exists rebase
   createdb --host=localhost --port=5432 --username=postgres rebase
   ```
4. **Restore Database from Custom Archive (`-Fc`):**
   ```powershell
   pg_restore --host=localhost --port=5432 --username=postgres --dbname=rebase "backups/rebase_phase8_prod_ready_20261105.dump"
   ```
5. **Execute Schema Migration Check:**
   ```bash
   cd backend
   python -m alembic check
   ```
   *Expected output: `No new upgrade operations detected.`*
6. **Restart Backend Service:**
   ```bash
   systemctl start rebase-backend.service
   ```
7. **Perform Smoke Verification:**
   - Query `/api/v1/health` and verify HTTP 200 with DB connected.

---

### SOP-DB-03: Alembic Schema Migration Drift Reconciliation

#### Procedure
If `alembic check` reports unexpected unmigrated operations:
1. Review generated migration differences:
   ```bash
   python -m alembic -c backend/alembic.ini revision --autogenerate -m "drift_reconciliation"
   ```
2. Inspect generated migration script under `backend/alembic/versions/` for:
   - Accidental `DROP TABLE` or `DROP COLUMN` on active audit logs or gate tables.
   - Type mismatches on UUID / GUID columns.
3. Apply migration cleanly:
   ```bash
   python -m alembic -c backend/alembic.ini upgrade head
   ```
4. Re-verify zero drift:
   ```bash
   python -m alembic -c backend/alembic.ini check
   ```

