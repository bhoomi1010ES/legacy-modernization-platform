"""CLI tool for running deterministic data consistency reconciliation."""

import argparse
import asyncio
import json
import os
import sys
from pathlib import Path

# Add backend directory to sys.path
backend_dir = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(backend_dir))

from app.core.database import AsyncSessionLocal
from app.services.reconciliation_service import ReconciliationService


async def run_reconciliation(apply_changes: bool = False, limit: int = 1000) -> None:
    print("=" * 80)
    print("   REBASE DATA CONSISTENCY RECONCILER (W03)")
    print(
        f"   Mode: {'APPLY (Transactional Batch)' if apply_changes else 'DRY RUN (Preview Only)'}"
    )
    print("=" * 80)

    async with AsyncSessionLocal() as session:
        # Step 1: Scan and generate manifest
        print("\nScanning database for historical contradictions...")
        manifest = await ReconciliationService.analyze(session, batch_limit=limit)

        print("\nPROPOSED ACTION SUMMARY:")
        print(f"  Batch ID:                {manifest.batch_id}")
        print(f"  Timestamp:               {manifest.timestamp}")
        print(f"  Total Actions Proposed:  {manifest.summary['total_actions']}")
        print(
            f"    - EVIDENCE_REVERIFY:       {manifest.summary['evidence_reverify']} (Unverified Modules)"
        )
        print(
            f"    - STALE_WORKER_QUARANTINE: {manifest.summary['stale_worker_quarantine']} (Expired RUNNING Attempts)"
        )
        print(
            f"    - GATE_RECONCILE:          {manifest.summary['gate_reconcile']} (Contradictory Pending Gates)"
        )
        print(
            f"    - DEADLETTER_REVIEW:       {manifest.summary['deadletter_review']} (Transient Dead-Letters)"
        )
        print(
            f"    - TERMINAL_RETAIN:         {manifest.summary['terminal_retain']} (Poison/Exhausted Dead-Letters)"
        )

        if not apply_changes:
            print("\nDRY RUN COMPLETE: Zero records were modified in the database.")
            print("To apply this reconciliation batch, run with: --apply")
            return

        # Step 2: Apply
        print("\nApplying reconciliation batch transactionally...")
        result = await ReconciliationService.apply(session, manifest)
        print("\nAPPLY COMPLETE:")
        print(f"  Batch ID:         {result['batch_id']}")
        print(f"  Status:           {result['status']}")
        print(f"  Applied Counts:   {json.dumps(result['applied_counts'], indent=2)}")
        print(
            "  Audit Event:      Appended to 'audit_events' table under event_type 'data.reconciliation_applied'"
        )


def main():
    parser = argparse.ArgumentParser(description="Rebase Data Consistency Reconciler")
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Apply reconciliation changes transactionally (default: dry run only)",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=1000,
        help="Max items to process for outbox dead-letter batch",
    )
    args = parser.parse_args()

    asyncio.run(run_reconciliation(apply_changes=args.apply, limit=args.limit))


if __name__ == "__main__":
    main()
