"""Submit the specifically reviewed G2 approval and let Supervisor/Planner prepare G3."""

import asyncio
import json
import logging
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402 -- standalone backend bootstrap above
from app.services.continuous_pipeline import continuous_pipeline_service  # noqa: E402

logger = logging.getLogger(__name__)


async def main() -> None:
    try:
        folder = ROOT / "artifacts/phase6-real-acceptance"
        review = json.loads((folder / "g2-review.json").read_text())
        job_id, gate = review["job_id"], review["g2"]
        if gate["gate_id"] != "7b8acf5b-804e-40f5-9d89-b57f5d3ce687":
            raise ValueError("Only the specific human-reviewed G2 may be submitted")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://acceptance.local",
            timeout=180,
        ) as client:
            client.cookies.update(
                json.loads((folder / "private-session.json").read_text())["cookies"]
            )
            before = await client.get(f"/api/v1/jobs/{job_id}/workflow")
            before.raise_for_status()
            decision = await client.post(
                f'/api/v1/gates/{gate["gate_id"]}/decision',
                json={
                    "decision": "APPROVED",
                    "rationale": "Human explicitly approved and froze suite v2 hash 61d3df2fff20f725f43821ae195d00ad6244c20f0ebce506431db7bca6b000d7 after reviewing four twice-executed legacy integer scenarios, matching side effects, no normalization, no known bugs, limited scenario-only coverage, and schema/data NOT_APPLICABLE.",
                    "artifact_hashes": gate["artifact_hashes"],
                    "idempotency_key": "phase6-real-human-g2-7b8acf5b",
                },
            )
            if decision.is_error:
                raise RuntimeError(f"Canonical G2 rejected: {decision.text}")
            task = continuous_pipeline_service._running_tasks.get(job_id)
            if task:
                await task
            plan = await client.get(f"/api/v1/jobs/{job_id}/conversion-plan")
            plan.raise_for_status()
            pending = await client.get("/api/v1/gates/pending")
            pending.raise_for_status()
            gates = [
                gate for gate in pending.json()["items"] if gate["job_id"] == job_id
            ]
            output = {
                "job_id": job_id,
                "before": before.json(),
                "g2_decision": decision.json(),
                "plan": plan.json(),
                "gates": gates,
            }
            (folder / "g3-review.json").write_text(
                json.dumps(output, sort_keys=True, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "job_id": job_id,
                        "g2_decision": decision.json(),
                        "plan": plan.json(),
                        "gates": [
                            {
                                key: gate[key]
                                for key in (
                                    "gate_id",
                                    "gate_type",
                                    "status",
                                    "artifact_hashes",
                                )
                            }
                            for gate in gates
                        ],
                    },
                    indent=2,
                )
            )
    except Exception:
        logger.exception("plan_job.main failed")
        raise


if __name__ == "__main__":
    asyncio.run(main())
