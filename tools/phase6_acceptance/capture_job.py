"""Record the user's specific G1 approval, then capture real legacy evidence for G2."""

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
        prepared = json.loads((folder / "prepare.json").read_text())
        job_id = prepared["job"]["job_id"]
        gate = prepared["gates"][0]
        if gate["gate_id"] != "75320b99-57c0-4bd4-9d9f-253bff28401c":
            raise ValueError("Only the specific user-reviewed G1 may be submitted")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://acceptance.local",
            timeout=180,
        ) as client:
            client.cookies.update(
                json.loads((folder / "private-session.json").read_text())["cookies"]
            )
            decision = await client.post(
                f'/api/v1/gates/{gate["gate_id"]}/decision',
                json={
                    "decision": "APPROVED",
                    "rationale": "Human explicitly approved this G1 evidence and fixture scope in conversation: pinned integer-only Python fixture; no production/data/HTTP dependencies; generic TypeScript/readiness text excluded. Qwen gateway reservation limited to 1 USD per attempt.",
                    "options": {
                        "legacy_adapter": "Approved pinned read-only Python integer-addition adapter; no dependency substitution or production access"
                    },
                    "artifact_hashes": gate["artifact_hashes"],
                    "idempotency_key": "phase6-real-human-g1-75320b99",
                },
            )
            if decision.is_error:
                raise RuntimeError(f"Gate API rejected reviewed G1: {decision.text}")
            task = continuous_pipeline_service._running_tasks.get(job_id)
            if task:
                await task
            analysis = prepared["analysis"]["legacy_model"]
            module = analysis["modules"][0]["module_id"]
            scenarios = [
                {
                    "name": "add",
                    "module": module,
                    "interface": "add(x:int,y:int)->int",
                    "behavior": "Preserve integer addition for positive, negative and zero values",
                    "inputs": inputs,
                }
                for inputs in (
                    {"x": 1, "y": 2},
                    {"x": -5, "y": 2},
                    {"x": 5, "y": -8},
                    {"x": 0, "y": 0},
                )
            ]
            capture = await client.post(
                f"/api/v1/jobs/{job_id}/characterization-runs",
                json={
                    "idempotency_key": "phase6-real-four-observed-cases-v1",
                    "scenarios": scenarios,
                    "environment": {
                        "notes": "Pinned offline image; integer-only adapters; no database connections or host mounts"
                    },
                },
            )
            capture.raise_for_status()
            report = capture.json()
            freeze = await client.post(
                f"/api/v1/jobs/{job_id}/g2/freeze",
                json={
                    "suite_id": report["suite_id"],
                    "content_hash": report["content_hash"],
                },
            )
            freeze.raise_for_status()
            schema = await client.get(f"/api/v1/jobs/{job_id}/schema-analysis")
            schema.raise_for_status()
            migration = await client.get(f"/api/v1/jobs/{job_id}/data-migration-plan")
            migration.raise_for_status()
            output = {
                "job_id": job_id,
                "g1_decision": decision.json(),
                "characterization": report,
                "schema": schema.json(),
                "migration": migration.json(),
                "g2": freeze.json(),
            }
            (folder / "g2-review.json").write_text(
                json.dumps(output, sort_keys=True, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "job_id": job_id,
                        "suite_id": report["suite_id"],
                        "version": report["version"],
                        "content_hash": report["content_hash"],
                        "cases": [
                            {
                                "id": case["test_case_id"],
                                "outcome": case["outcome"],
                                "expected": case["expected"],
                            }
                            for case in report["cases"]
                        ],
                        "coverage": report["coverage"],
                        "schema_status": report["schema_status"],
                        "g2": freeze.json(),
                    },
                    indent=2,
                )
            )
    except Exception:
        logger.exception("capture_job.main failed")
        raise


if __name__ == "__main__":
    asyncio.run(main())
