from pathlib import Path

p = Path("LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md")
text = p.read_text(encoding="utf-8")

# 1. Update Section 2 Table
old_table = """| Workstream | Severity | Dependencies | Required before |
|---|---|---|---|
| W00 Freeze + evidence capture | P0 | None | Any mutation |
| W01 Authentication/RBAC/gates/artifacts | P0 | W00 | Public/production use |
| W02 Safe CI + isolated runtime fixtures | P0 | W00 | Meaningful regression testing |
| W03 Schema/roles/state reconciliation | P0/P1 | W00, W02 | Clean deployment |
| W04 Single authoritative supervisor | P0/P1 | W01, W03 | Full pipeline acceptance |
| W05 Durable dispatch/lease/recovery | P0/P1 | W03, W04 | Parallel workers |
| W06 Common agent contracts/provenance | P1 | W04, W05 | Evidence-based G1–G4 |
| W07 Real characterization and Schema/Data | P0/P1 | W02, W06 | G2 and planning |
| W08 Constraint-aware Planner/DAG | P1 | W07 | G3 and conversion |
| W09 CodeWriter and hardened sandbox | P0/P1 | W01, W05, W08 | Real conversion acceptance |
| W10 Independent verification / Reviewer | P0/P1 | W07, W09 | Verified module status |
| W11 Integrator / G4 / release evidence | P1 | W10 | User delivery |
| W12 Truthful frontend projections | P1 | W04, W06, W10 | Human approvals |
| W13 Production deployment, ops and security | P1/P2 | All critical workstreams | Public GA |
| W14 Final kill/fault/E2E/scale certification | P0/P1 | W01–W13 | Production-ready label |"""

new_table = """| Workstream | Severity | Dependencies | Required before | Status |
|---|---|---|---|---|
| W00 Freeze + evidence capture | P0 | None | Any mutation | **COMPLETED & SIGNED OFF** |
| W01 Authentication/RBAC/gates/artifacts | P0 | W00 | Public/production use | **COMPLETED & SIGNED OFF** |
| W02 Safe CI + isolated runtime fixtures | P0 | W00 | Meaningful regression testing | Ready to Start |
| W03 Schema/roles/state reconciliation | P0/P1 | W00, W02 | Clean deployment | Pending |
| W04 Single authoritative supervisor | P0/P1 | W01, W03 | Full pipeline acceptance | Pending |
| W05 Durable dispatch/lease/recovery | P0/P1 | W03, W04 | Parallel workers | Pending |
| W06 Common agent contracts/provenance | P1 | W04, W05 | Evidence-based G1–G4 | Pending |
| W07 Real characterization and Schema/Data | P0/P1 | W02, W06 | G2 and planning | Pending |
| W08 Constraint-aware Planner/DAG | P1 | W07 | G3 and conversion | Pending |
| W09 CodeWriter and hardened sandbox | P0/P1 | W01, W05, W08 | Real conversion acceptance | Pending |
| W10 Independent verification / Reviewer | P0/P1 | W07, W09 | Verified module status | Pending |
| W11 Integrator / G4 / release evidence | P1 | W10 | User delivery | Pending |
| W12 Truthful frontend projections | P1 | W04, W06, W10 | Human approvals | Pending |
| W13 Production deployment, ops and security | P1/P2 | All critical workstreams | Public GA | Pending |
| W14 Final kill/fault/E2E/scale certification | P0/P1 | W01–W13 | Production-ready label | Pending |"""

# 2. Update Section 3 Header and Exit
old_sec3 = """## 3. W00 — Freeze, preserve, verify the audit (before edits)

**Goal:** Get a reproducible starting state without damaging persistent data."""

new_sec3 = """## 3. W00 — Freeze, preserve, verify the audit (before edits)

> **STATUS:** **COMPLETED & SIGNED OFF**  
> **Sign-Off Date:** 2026-10-30  
> **Baseline Commit:** `3e69b506a3149509d791120ae785d0c1e4bed2a1` (`main`)  
> **Execution Environment:** `ENV-LOCAL-DEV-POSTGRES18`  
> **Verified Evidence Package:**
> - Baseline Snapshot Metadata: [`docs/remediation/w00/SNAPSHOT_METADATA.md`](docs/remediation/w00/SNAPSHOT_METADATA.md)
> - Database Backup & Restoration: [`docs/remediation/w00/DATABASE_BACKUP_AND_RESTORE_VERIFICATION.md`](docs/remediation/w00/DATABASE_BACKUP_AND_RESTORE_VERIFICATION.md) (Custom dump `backups/rebase_w00_freeze_20261030.dump`, SHA-256 `40F40911F9275B22D9810C3B86A7D89456FD646BE82F7768DF9882E00DD7740E`; 36/36 tables and 279,432/279,432 rows 100% verified)
> - Read-Only State Summaries: [`docs/remediation/w00/READ_ONLY_STATE_SUMMARIES.md`](docs/remediation/w00/READ_ONLY_STATE_SUMMARIES.md) (Jobs, Gates, Modules, Leases, Checkpoints, Outbox, Lineage breaks)
> - Artifact Manifest: [`docs/remediation/w00/ARTIFACT_MANIFEST.md`](docs/remediation/w00/ARTIFACT_MANIFEST.md) & `.json` (17,458 workspace artifacts hashed)
> - Remediation Evidence Ledger: [`docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md`](docs/remediation/w00/REMEDIATION_EVIDENCE_LEDGER.md) (32/32 findings cataloged 1:1: `SEC-01`–`08`, `FLOW-01`–`07`, `DATA-01`–`07`, `TEST-01`–`05`, `UI-01`–`05`)

**Goal:** Get a reproducible starting state without damaging persistent data."""

old_exit = """**Exit:** Signed-off snapshot + recoverable backup + 1:1 issue ledger."""
new_exit = """**Exit:** Signed-off snapshot + recoverable backup + 1:1 issue ledger.  
**Exit Verification Outcome:** **PASSED & SIGNED OFF (2026-10-30)**. All 6 step-by-step requirements and all 3 verification criteria validated without errors."""

if old_table in text:
    text = text.replace(old_table, new_table)
elif old_table.replace("\n", "\r\n") in text:
    text = text.replace(old_table.replace("\n", "\r\n"), new_table.replace("\n", "\r\n"))

if old_sec3 in text:
    text = text.replace(old_sec3, new_sec3)
elif old_sec3.replace("\n", "\r\n") in text:
    text = text.replace(old_sec3.replace("\n", "\r\n"), new_sec3.replace("\n", "\r\n"))

if old_exit in text:
    text = text.replace(old_exit, new_exit)
elif old_exit.replace("\n", "\r\n") in text:
    text = text.replace(old_exit.replace("\n", "\r\n"), new_exit.replace("\n", "\r\n"))

p.write_text(text, encoding="utf-8")
print("Successfully updated LEGACY_PLATFORM_REMEDIATION_IMPLEMENTATION_PLAN.md")

