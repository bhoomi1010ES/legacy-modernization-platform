"""Create the user-authorized disposable account/job through normal APIs; stop at G1."""

import asyncio
import json
import logging
from pathlib import Path
import secrets
import subprocess
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
        folder.mkdir(exist_ok=True)
        session_path = folder / "private-session.json"
        output_path = folder / "prepare.json"
        source = ROOT / "artifacts/phase6-acceptance-source-runtime"
        commit = subprocess.run(
            ["git", "-C", str(source), "rev-parse", "HEAD"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app),
            base_url="http://acceptance.local",
            timeout=120,
        ) as client:
            if session_path.exists():
                client.cookies.update(json.loads(session_path.read_text())["cookies"])
            else:
                account = await client.post(
                    "/api/v1/auth/register",
                    json={
                        "email": f"phase6-acceptance-{uuid.uuid4().hex[:10]}@example.com",
                        "full_name": "Disposable Phase 6 Acceptance",
                        "password": secrets.token_urlsafe(32),
                        "role": "ADMIN",
                    },
                )
                account.raise_for_status()
                session_path.write_text(
                    json.dumps(
                        {
                            "user_id": account.json()["user_id"],
                            "cookies": dict(client.cookies),
                        }
                    ),
                    encoding="utf-8",
                )
            if output_path.exists():
                output = json.loads(output_path.read_text())
            else:
                created = await client.post(
                    "/api/v1/jobs",
                    json={
                        "name": "Phase 6 real acceptance - integer calculator",
                        "source_repository": source.as_uri(),
                        "source_type": "git",
                        "source_revision": commit,
                        "pinned_commit": commit,
                        "source_stack": "Python 3.12",
                        "target_stack": "Python 3.12",
                        "budget": 50,
                        "max_repair_attempts": 1,
                        "constraints": "Disposable integer-only add(x:int,y:int)->int fixture. Implement calc.py inside the approved target module directory. Preserve negative/zero/positive integer addition. No HTTP server, database, external dependencies, or production access. Use existing OpenRouter allowlisted Qwen Coder, reservation <=1 USD per attempt; no other external model calls.",
                    },
                )
                created.raise_for_status()
                output = {
                    "job": created.json(),
                    "source_commit": commit,
                    "api_evidence": [],
                }
                output_path.write_text(json.dumps(output, indent=2), encoding="utf-8")
            job_id = output["job"]["job_id"]
            workflow = (await client.get(f"/api/v1/jobs/{job_id}/workflow")).json()
            if workflow["status"] == "CREATED":
                intake = await client.post(f"/api/v1/jobs/{job_id}/intake", json={})
                output["api_evidence"].append(
                    {"endpoint": "intake", "status": intake.status_code}
                )
                intake.raise_for_status()
                workflow = (await client.get(f"/api/v1/jobs/{job_id}/workflow")).json()
            if workflow["status"] in ("INTAKE", "ANALYZING"):
                analysis = await client.post(
                    f"/api/v1/jobs/{job_id}/analysis/retry",
                    json={
                        "reason": "Run initial analysis of the approved disposable acceptance fixture"
                    },
                )
                output["api_evidence"].append(
                    {"endpoint": "analysis/retry", "status": analysis.status_code}
                )
                analysis.raise_for_status()
            for name in (
                "repository",
                "analysis",
                "blueprint",
                "feasibility",
                "workflow",
            ):
                response = await client.get(f"/api/v1/jobs/{job_id}/{name}")
                output["api_evidence"].append(
                    {"endpoint": name, "status": response.status_code}
                )
                response.raise_for_status()
                output[name] = response.json()
            pending = await client.get("/api/v1/gates/pending")
            pending.raise_for_status()
            output["gates"] = [
                gate for gate in pending.json()["items"] if gate["job_id"] == job_id
            ]
            output_path.write_text(
                json.dumps(output, indent=2, sort_keys=True), encoding="utf-8"
            )
            print(
                json.dumps(
                    {
                        "job_id": job_id,
                        "status": output["workflow"]["status"],
                        "source_commit": commit,
                        "gates": output["gates"],
                    },
                    indent=2,
                )
            )
    except Exception:
        logger.exception("prepare_job.main failed")
        raise


if __name__ == "__main__":
    asyncio.run(main())
