"""Real authenticated/IDOR checks. Leave the unfunded job paused, not falsely successful."""

import asyncio
import json
import logging
from pathlib import Path
import secrets
import sys
import uuid

import httpx

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.main import app  # noqa: E402 -- standalone harness bootstraps backend imports

logger = logging.getLogger(__name__)


async def main() -> None:
    try:
        folder = ROOT / "artifacts/phase6-real-acceptance"
        conversion = json.loads((folder / "conversion.json").read_text())
        job_id, module_id = conversion["job_id"], conversion["module_id"]
        attempt_id = conversion["board"]["items"][0]["attempt_id"]
        endpoints = [("GET", f"/jobs/{job_id}/module-attempts", None)]
        endpoints += [
            ("GET", f"/module-attempts/{attempt_id}{suffix}", None)
            for suffix in ("", "/diff", "/test-results", "/review")
        ]
        endpoints += [
            (
                "POST",
                f"/jobs/{job_id}/modules/{module_id}/conversion-runs",
                {"idempotency_key": "unauthorized-acceptance-probe"},
            ),
            (
                "POST",
                f"/module-attempts/{attempt_id}/repair",
                {
                    "idempotency_key": "unauthorized-repair-probe",
                    "rationale": "Unauthorized negative acceptance check only",
                },
            ),
            (
                "POST",
                f"/module-attempts/{attempt_id}/waivers",
                {
                    "finding_id": "nonexistent-finding",
                    "rationale": "Unauthorized negative acceptance check only",
                },
            ),
        ]
        records = []
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://acceptance.local"
        ) as client:
            for method, endpoint, payload in endpoints:
                response = await client.request(
                    method, "/api/v1" + endpoint, json=payload
                )
                if response.status_code != 401:
                    raise RuntimeError(
                        f"Unauthenticated resource access not denied: {endpoint}"
                    )
                records.append(
                    {
                        "actor": "unauthenticated",
                        "method": method,
                        "endpoint": endpoint,
                        "status": response.status_code,
                    }
                )
            account = await client.post(
                "/api/v1/auth/register",
                json={
                    "email": f"phase6-outsider-{uuid.uuid4().hex[:10]}@example.com",
                    "full_name": "Disposable Acceptance Outsider",
                    "password": secrets.token_urlsafe(32),
                    "role": "VIEWER",
                },
            )
            account.raise_for_status()
            for method, endpoint, payload in endpoints:
                response = await client.request(
                    method, "/api/v1" + endpoint, json=payload
                )
                if response.status_code not in (403, 404):
                    raise RuntimeError(
                        f"Cross-job access not denied: {endpoint} status {response.status_code}"
                    )
                records.append(
                    {
                        "actor": "authenticated_nonmember",
                        "method": method,
                        "endpoint": endpoint,
                        "status": response.status_code,
                    }
                )
            await client.post("/api/v1/auth/logout")
            client.cookies.clear()
            client.cookies.update(
                json.loads((folder / "private-session.json").read_text())["cookies"]
            )
            for method, endpoint, payload in endpoints:
                if method == "GET":
                    response = await client.get("/api/v1" + endpoint)
                    response.raise_for_status()
                    records.append(
                        {
                            "actor": "job_owner",
                            "method": method,
                            "endpoint": endpoint,
                            "status": response.status_code,
                        }
                    )
            # No model retries after the user chose to leave model acceptance pending.
            paused = await client.post(f"/api/v1/jobs/{job_id}/pause")
            paused.raise_for_status()
            blocked_repair = await client.post(
                f"/api/v1/module-attempts/{attempt_id}/repair",
                json={
                    "idempotency_key": "phase6-paused-repair-must-block",
                    "rationale": "User left model acceptance pending; paused workflow must not schedule a retry",
                },
            )
            if blocked_repair.status_code != 409:
                raise RuntimeError("Paused job did not block repair")
            waiver = await client.post(
                f"/api/v1/module-attempts/{attempt_id}/waivers",
                json={
                    "finding_id": "nonexistent-finding",
                    "rationale": "Missing execution cannot be waived by inventing a reviewer finding",
                },
            )
            if waiver.status_code != 404:
                raise RuntimeError("Fabricated finding was not rejected")
            records += [
                {
                    "actor": "job_owner_paused",
                    "method": "POST",
                    "endpoint": "/repair",
                    "status": blocked_repair.status_code,
                },
                {
                    "actor": "job_owner",
                    "method": "POST",
                    "endpoint": "/waivers",
                    "status": waiver.status_code,
                },
            ]
            events = await client.get(f"/api/v1/jobs/{job_id}/events?limit=500")
            events.raise_for_status()
            report = {
                "job_id": job_id,
                "job_status": paused.json()["status"],
                "checks": records,
                "events": events.json(),
            }
            (folder / "api-checks.json").write_text(
                json.dumps(report, sort_keys=True, indent=2), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "job_id": job_id,
                        "status": report["job_status"],
                        "checks": records,
                        "event_count": len(events.json()["items"]),
                    },
                    indent=2,
                )
            )
    except Exception:
        logger.exception("api_checks.main failed")
        raise


if __name__ == "__main__":
    asyncio.run(main())
