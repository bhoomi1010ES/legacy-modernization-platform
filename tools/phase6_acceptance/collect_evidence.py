"""Read-only verification of the real job's persisted hashes, gates and Git lineage."""

import asyncio
import hashlib
import json
import logging
from pathlib import Path
import sys
import uuid

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from sqlalchemy import select  # noqa: E402 -- standalone backend bootstrap
from app.core.database import AsyncSessionLocal  # noqa: E402
from app.core.storage import get_storage_adapter  # noqa: E402
from app.models.agent import AgentRun  # noqa: E402
from app.models.artifact import Artifact  # noqa: E402
from app.models.job import Job  # noqa: E402
from app.models.module import ModuleAttempt  # noqa: E402
from app.models.test_case import TestCase, TestResult  # noqa: E402
from app.models.workflow import WorkflowGate  # noqa: E402
from app.services import phase6_workspace as workspace  # noqa: E402
from app.services.reviewer_agent import review  # noqa: E402

logger = logging.getLogger(__name__)


async def main() -> None:
    try:
        folder = ROOT / "artifacts/phase6-real-acceptance"
        conversion = json.loads((folder / "conversion.json").read_text())
        job_id = uuid.UUID(conversion["job_id"])
        async with AsyncSessionLocal() as db:
            job = await db.get(Job, job_id)
            artifacts = list(
                (
                    await db.execute(
                        select(Artifact)
                        .where(Artifact.job_id == job_id)
                        .order_by(Artifact.created_at)
                    )
                ).scalars()
            )
            entries = []
            for artifact in artifacts:
                raw = await get_storage_adapter().get_object(artifact.storage_path)
                actual = hashlib.sha256(raw).hexdigest()
                if actual != artifact.content_hash:
                    raise RuntimeError(
                        "Real artifact bytes failed SHA-256 verification"
                    )
                entries.append(
                    {
                        "artifact_id": str(artifact.artifact_id),
                        "type": artifact.artifact_type,
                        "version": artifact.version,
                        "sha256": actual,
                        "size": len(raw),
                        "storage_path": artifact.storage_path,
                    }
                )
            gates = list(
                (
                    await db.execute(
                        select(WorkflowGate)
                        .where(WorkflowGate.job_id == job_id)
                        .order_by(WorkflowGate.requested_at)
                    )
                ).scalars()
            )
            attempt_id = uuid.UUID(conversion["board"]["items"][0]["attempt_id"])
            attempt = await db.get(ModuleAttempt, attempt_id)
            run = await db.get(AgentRun, attempt.agent_run_id)
            cases = list(
                (
                    await db.execute(
                        select(TestCase).where(
                            TestCase.job_id == job_id, TestCase.is_frozen.is_(True)
                        )
                    )
                ).scalars()
            )
            results = list(
                (
                    await db.execute(
                        select(TestResult).where(TestResult.attempt_id == attempt_id)
                    )
                ).scalars()
            )
            repo = workspace.repository_for(str(job_id))
            branch_commit = await workspace.git(repo, "rev-parse", attempt.git_branch)
            worktrees = await workspace.git(repo, "worktree", "list", "--porcelain")
            environment = json.loads((folder / "environment.json").read_text())
            probe_review = review(
                {
                    environment[
                        "target_path"
                    ]: "def add(x: int, y: int) -> int:\n    return x + y\n"
                },
                [{"symbol": "add"}],
                environment["verification"]["artifact_hash"],
                execution=environment["verification"],
            )
            output = {
                "job_id": str(job_id),
                "job_status": job.status,
                "paused_from": job.paused_from_status,
                "attempt_id": str(attempt_id),
                "attempt_status": attempt.status,
                "branch": attempt.git_branch,
                "branch_commit": branch_commit,
                "worktree_list": worktrees,
                "run_id": str(run.run_id),
                "provider": run.model_provider,
                "model": run.model_identifier,
                "run_status": run.status,
                "started_at": run.started_at.isoformat(),
                "completed_at": run.completed_at.isoformat(),
                "cost_reservation": run.task_payload.get("cost_reservation"),
                "plan_hash": run.task_payload.get("plan_hash"),
                "baseline_hash": run.task_payload.get("baseline_hash"),
                "source_commit": run.task_payload.get("source_commit"),
                "model_usage_status": "NOT_RETURNED: provider rejected request with HTTP 402",
                "attempt_test_result_count": len(results),
                "frozen_case_ids": [str(case.test_case_id) for case in cases],
                "artifacts": entries,
                "gates": [
                    {
                        "gate_id": str(gate.gate_id),
                        "type": gate.gate_type,
                        "version": gate.version,
                        "status": gate.status,
                        "hashes": gate.artifact_hashes,
                    }
                    for gate in gates
                ],
                "probe_review": probe_review,
                "probe_review_scope": "Trusted code probe only; not real CodeWriter output",
            }
            (folder / "persistence.json").write_text(
                json.dumps(output, sort_keys=True, indent=2), encoding="utf-8"
            )
            print(json.dumps(output, sort_keys=True, indent=2))
    except Exception:
        logger.exception("collect_evidence.main failed")
        raise


if __name__ == "__main__":
    asyncio.run(main())
