"""Reject caller execution controls/results through real, authenticated API validation."""

import asyncio
import json
import logging
from pathlib import Path
import sys

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402 -- standalone backend bootstrap

logger = logging.getLogger(__name__)


async def main() -> None:
    try:
        folder = ROOT / "artifacts/phase6-real-acceptance"
        state = json.loads((folder / "conversion.json").read_text())
        attempt_id = state["board"]["items"][0]["attempt_id"]
        cases = [
            (
                f'/jobs/{state["job_id"]}/modules/{state["module_id"]}/conversion-runs',
                {
                    "idempotency_key": "denied-command",
                    "command": ["sh", "-c", "echo fabricated"],
                },
            ),
            (
                f'/jobs/{state["job_id"]}/modules/{state["module_id"]}/conversion-runs',
                {"idempotency_key": "denied-result", "verification": {"passed": True}},
            ),
            (
                f"/module-attempts/{attempt_id}/repair",
                {
                    "idempotency_key": "denied-repair-command",
                    "rationale": "Controlled negative request; never execute",
                    "argv": ["sh"],
                },
            ),
            (
                f"/module-attempts/{attempt_id}/waivers",
                {
                    "finding_id": "invented",
                    "rationale": "Controlled negative waiver request",
                    "verified": True,
                },
            ),
        ]
        results = []
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://acceptance.local"
        ) as client:
            client.cookies.update(
                json.loads((folder / "private-session.json").read_text())["cookies"]
            )
            for endpoint, payload in cases:
                response = await client.post("/api/v1" + endpoint, json=payload)
                if response.status_code != 422:
                    raise RuntimeError(
                        "Caller controls/evidence were not rejected by strict API schema"
                    )
                results.append(
                    {
                        "endpoint": endpoint,
                        "status": response.status_code,
                        "error": response.json(),
                    }
                )
        (folder / "payload-checks.json").write_text(
            json.dumps(results, sort_keys=True, indent=2), encoding="utf-8"
        )
        print(json.dumps(results, indent=2))
    except Exception:
        logger.exception("check_payloads.main failed")
        raise


if __name__ == "__main__":
    asyncio.run(main())
