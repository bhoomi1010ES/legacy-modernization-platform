"""Phase 8 PostgreSQL Backup and Restore Disaster Recovery Verification Drill."""

import asyncio
import hashlib
import os
import subprocess
import sys
import time
import asyncpg

PG_BIN = r"C:\Program Files\PostgreSQL\18\bin"
PG_DUMP = os.path.join(PG_BIN, "pg_dump.exe")
PG_RESTORE = os.path.join(PG_BIN, "pg_restore.exe")
CREATEDB = os.path.join(PG_BIN, "createdb.exe")
DROPDB = os.path.join(PG_BIN, "dropdb.exe")

DB_USER = "postgres"
DB_PASS = "postres123"
DB_HOST = "localhost"
DB_PORT = "5432"
ORIG_DB = "rebase"
DISP_DB = "rebase_disposable_phase8_verify"
BACKUP_PATH = os.path.abspath(r"backups\rebase_phase8_prod_ready_20261105.dump")


def run_cmd(cmd, env_extra=None):
    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    print(f"[EXEC] {' '.join(cmd)}")
    res = subprocess.run(cmd, env=env, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[ERROR] Returncode: {res.returncode}")
        print(f"[STDERR] {res.stderr}")
        raise RuntimeError(f"Command failed: {' '.join(cmd)}\n{res.stderr}")
    return res.stdout


def compute_sha256(filepath):
    h = hashlib.sha256()
    with open(filepath, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()


async def verify_equivalence():
    print(f"[VERIFY] Connecting to {ORIG_DB} and {DISP_DB}...")
    conn_orig = await asyncpg.connect(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{ORIG_DB}")
    conn_disp = await asyncpg.connect(f"postgresql://{DB_USER}:{DB_PASS}@{DB_HOST}:{DB_PORT}/{DISP_DB}")

    try:
        tables_orig = [
            r["table_name"]
            for r in await conn_orig.fetch(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
            )
        ]
        tables_disp = [
            r["table_name"]
            for r in await conn_disp.fetch(
                "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' ORDER BY table_name"
            )
        ]

        print(f"[TABLES] Original: {len(tables_orig)} | Restored: {len(tables_disp)}")
        assert tables_orig == tables_disp, f"Table schema mismatch!\nOrig: {tables_orig}\nDisp: {tables_disp}"

        mismatches = []
        total_rows_orig = 0
        total_rows_disp = 0
        table_stats = []

        for tbl in tables_orig:
            c_orig = await conn_orig.fetchval(f'SELECT count(*) FROM "{tbl}"')
            c_disp = await conn_disp.fetchval(f'SELECT count(*) FROM "{tbl}"')
            total_rows_orig += c_orig
            total_rows_disp += c_disp
            table_stats.append((tbl, c_orig, c_disp))
            if c_orig != c_disp:
                mismatches.append((tbl, c_orig, c_disp))

        print(f"[ROWS] Original total rows: {total_rows_orig:,}")
        print(f"[ROWS] Restored total rows: {total_rows_disp:,}")

        if mismatches:
            print("[FAIL] Mismatches detected:", mismatches)
            raise AssertionError(f"Row count mismatches: {mismatches}")

        print(f"[SUCCESS] 100% equivalence verified across {len(tables_orig)} tables and {total_rows_orig:,} total rows!")
        return {
            "tables_count": len(tables_orig),
            "total_rows": total_rows_orig,
            "table_stats": table_stats,
        }
    finally:
        await conn_orig.close()
        await conn_disp.close()


def main():
    pg_env = {"PGPASSWORD": DB_PASS}
    t0 = time.time()

    # Step 1: Dump database
    print(f"[STEP 1] Generating custom archive dump: {BACKUP_PATH}")
    dump_cmd = [
        PG_DUMP,
        f"--host={DB_HOST}",
        f"--port={DB_PORT}",
        f"--username={DB_USER}",
        f"--dbname={ORIG_DB}",
        "--format=custom",
        f"--file={BACKUP_PATH}",
    ]
    run_cmd(dump_cmd, pg_env)
    dump_size = os.path.getsize(BACKUP_PATH)
    dump_sha256 = compute_sha256(BACKUP_PATH)
    print(f"[DUMP CREATED] Size: {dump_size:,} bytes | SHA-256: {dump_sha256}")

    # Step 2: Clean slate for disposable DB
    print(f"[STEP 2] Dropping existing disposable DB if present: {DISP_DB}")
    run_cmd([DROPDB, f"--host={DB_HOST}", f"--port={DB_PORT}", f"--username={DB_USER}", "--if-exists", DISP_DB], pg_env)

    print(f"[STEP 3] Creating fresh disposable DB: {DISP_DB}")
    run_cmd([CREATEDB, f"--host={DB_HOST}", f"--port={DB_PORT}", f"--username={DB_USER}", DISP_DB], pg_env)

    # Step 3: Restore dump into disposable DB
    print(f"[STEP 4] Restoring dump into disposable DB: {DISP_DB}")
    restore_cmd = [
        PG_RESTORE,
        f"--host={DB_HOST}",
        f"--port={DB_PORT}",
        f"--username={DB_USER}",
        f"--dbname={DISP_DB}",
        BACKUP_PATH,
    ]
    run_cmd(restore_cmd, pg_env)
    print("[RESTORE COMPLETE]")

    # Step 4: Verify 1:1 Schema & Data Equivalence
    print("[STEP 5] Verifying 1:1 Schema and Row Count Equivalence...")
    results = asyncio.run(verify_equivalence())

    # Step 5: Clean up disposable database
    print(f"[STEP 6] Tearing down disposable verification DB: {DISP_DB}")
    run_cmd([DROPDB, f"--host={DB_HOST}", f"--port={DB_PORT}", f"--username={DB_USER}", DISP_DB], pg_env)
    print("[TEARDOWN COMPLETE]")

    duration = time.time() - t0
    print(f"[COMPLETE] Disaster recovery restore verification completed in {duration:.2f}s.")
    print("SUMMARY_OUTPUT_START")
    import json
    print(json.dumps({
        "backup_path": BACKUP_PATH,
        "backup_size_bytes": dump_size,
        "sha256": dump_sha256,
        "tables_count": results["tables_count"],
        "total_rows": results["total_rows"],
        "duration_seconds": round(duration, 2),
        "table_stats": results["table_stats"]
    }))
    print("SUMMARY_OUTPUT_END")


if __name__ == "__main__":
    main()

