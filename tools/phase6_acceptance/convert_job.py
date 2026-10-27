"""Record the specific human G3 approval; execute the real Supervisor/model/Docker path."""

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
        reviewed = json.loads((folder / "g3-review.json").read_text())
        job_id, gate = reviewed["job_id"], reviewed["gates"][0]
        if gate["gate_id"] != "3dfb1e63-fb34-4889-8f89-8fca69389b4d":
            raise ValueError("Only the specific human-reviewed G3 may be submitted")
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://acceptance.local",
            timeout=600,
        ) as client:
            client.cookies.update(
                json.loads((folder / "private-session.json").read_text())["cookies"]
            )
            board = await client.get(f"/api/v1/jobs/{job_id}/module-attempts")
            board.raise_for_status()
            module_id = board.json()["modules"][0]["module_id"]
            before = await client.post(
                f"/api/v1/jobs/{job_id}/modules/{module_id}/conversion-runs",
                json={"idempotency_key": "phase6-real-pre-g3-must-block"},
            )
            if before.status_code != 409:
                raise RuntimeError("Conversion did not refuse pending G3")
            decision = await client.post(
                f'/api/v1/gates/{gate["gate_id"]}/decision',
                json={
                    "decision": "APPROVED",
                    "rationale": "Human explicitly approved this G3 bounded conversion plan and hash-bound Python integer calculator scope in conversation. Generic HTTP tasks are not applicable to the G1 contract. Existing allowlisted Qwen Coder only; maximum initial plus one repair at <=1 USD per attempt. Integration/G4 must remain blocked without real integration evidence.",
                    "artifact_hashes": gate["artifact_hashes"],
                    "idempotency_key": "phase6-real-human-g3-3dfb1e63",
                },
            )
            if decision.is_error:
                raise RuntimeError(f"Canonical G3 rejected: {decision.text}")
            task = continuous_pipeline_service._running_tasks.get(job_id)
            if task:
                await task
            board = await client.get(f"/api/v1/jobs/{job_id}/module-attempts")
            board.raise_for_status()
            workflow = await client.get(f"/api/v1/jobs/{job_id}/workflow")
            workflow.raise_for_status()
            output = {
                "job_id": job_id,
                "module_id": module_id,
                "pending_g3_conversion_response": {
                    "status": before.status_code,
                    "body": before.json(),
                },
                "g3_decision": decision.json(),
                "workflow": workflow.json(),
                "board": board.json(),
                "attempt_api_evidence": [],
            }
            for attempt in board.json()["items"]:
                attempt_id = attempt["attempt_id"]
                for suffix in ("", "/diff", "/test-results", "/review"):
                    response = await client.get(
                        f"/api/v1/module-attempts/{attempt_id}{suffix}"
                    )
                    output["attempt_api_evidence"].append(
                        {
                            "attempt_id": attempt_id,
                            "endpoint": suffix or "/detail",
                            "status": response.status_code,
                            "body": response.json(),
                        }
                    )
            (folder / "conversion.json").write_text(
                json.dumps(output, sort_keys=True, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "job_id": job_id,
                        "module_id": module_id,
                        "workflow_status": workflow.json()["status"],
                        "pending_g3_blocked": before.status_code,
                        "attempts": [
                            {
                                "attempt_id": attempt["attempt_id"],
                                "status": attempt["status"],
                                "failure_reason": attempt.get("failure_reason"),
                                "model": attempt.get("agent"),
                                "evidence": attempt["evidence"],
                            }
                            for attempt in board.json()["items"]
                        ],
                    },
                    sort_keys=True,
                    indent=2,
                )
            )
    except Exception:
        logger.exception("convert_job.main failed")
        raise


if __name__ == "__main__":
    asyncio.run(main())
