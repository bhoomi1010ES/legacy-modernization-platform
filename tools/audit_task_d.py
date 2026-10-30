import asyncio
import hashlib
import json
import subprocess
import sys
import uuid
from pathlib import Path
from sqlalchemy import select

sys.path.insert(0, str(Path("backend").resolve()))

from app.core.database import AsyncSessionLocal
from app.models.module import Module, ModuleAttempt
from app.models.artifact import Artifact
from app.models.agent import AgentRun

JOB_ID = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
MODULE_ID = uuid.UUID("8a53e2d8-e298-5112-a9a7-cca8fe8cc3c3")
ATTEMPT_4_ID = uuid.UUID("aadd09e9-9381-46db-a4b8-d9b5c41fcf3a")
CANONICAL_REPO = Path("repo_workspaces/job_eb2bbaa9-90ee-4e9d-b340-5e025594126c").resolve()
EXPECTED_COMMIT = "531f76a56424cea4c2ebc773b8cd649536a7d8b0"
BASE_COMMIT = "9a27078f28ac842cf4cd0e002d7a9a863331f390"

def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as f:
        while chunk := f.read(65536):
            h.update(chunk)
    return h.hexdigest()

async def run():
    print("="*80)
    print("TASK D: VALIDATE CHANGESET AND ARTIFACT PROVENANCE")
    print("="*80)

    async with AsyncSessionLocal() as session:
        # 1. Attempt 4
        attempt = await session.get(ModuleAttempt, ATTEMPT_4_ID)
        print(f"Attempt 4 ID: {attempt.attempt_id}")
        print(f"Status: {attempt.status}")
        print(f"Git branch: {attempt.git_branch}")
        print(f"Agent Run ID: {attempt.agent_run_id}")

        # 2. Agent Run 4
        if attempt.agent_run_id:
            run_obj = await session.get(AgentRun, attempt.agent_run_id)
            print(f"\nAgent Run: {run_obj.run_id}")
            print(f"Status: {run_obj.status}")
            print(f"Agent Name: {run_obj.agent_name}")
            print(f"Model Identifier: {run_obj.model_identifier}")
            print(f"Input Tokens: {run_obj.input_tokens}, Output Tokens: {run_obj.output_tokens}, Cost USD: {run_obj.cost_usd}")
            print(f"Input Artifact Refs: {run_obj.input_artifact_refs}")
            print(f"Output Artifact Refs: {run_obj.output_artifact_refs}")
            print(f"Output Payload:")
            print(json.dumps(run_obj.output_payload or {}, indent=2))

        # 3. Artifacts for this module / job
        stmt = select(Artifact).where(Artifact.job_id == JOB_ID).order_by(Artifact.created_at)
        artifacts = (await session.execute(stmt)).scalars().all()
        print(f"\nTotal Artifacts for Job {JOB_ID}: {len(artifacts)}")

        module_artifacts = [a for a in artifacts if a.module_id == MODULE_ID or (a.extra_metadata and a.extra_metadata.get("module_id") == str(MODULE_ID))]
        print(f"Artifacts related to Module {MODULE_ID}: {len(module_artifacts)}")

        for art in module_artifacts:
            print(f"\n--- Artifact: {art.artifact_type} ({art.artifact_id}) ---")
            print(f"Version: {art.version}")
            print(f"Producing Agent: {art.producing_agent}")
            print(f"Content Hash (DB): {art.content_hash}")
            print(f"Storage Path: {art.storage_path}")
            print(f"Size in DB: {art.content_size_bytes}")
            print(f"Extra Metadata: {art.extra_metadata}")

            # Check file on disk
            candidates = [
                Path(art.storage_path),
                Path("artifacts") / art.storage_path,
                Path("artifacts/jobs") / str(JOB_ID) / art.storage_path,
                Path("artifacts/jobs") / str(JOB_ID) / f"{art.artifact_id}.json",
                Path("backend") / art.storage_path,
            ]
            found_path = None
            for c in candidates:
                if c.exists() and c.is_file():
                    found_path = c
                    break
            
            if found_path:
                disk_hash = sha256_file(found_path)
                disk_size = found_path.stat().st_size
                print(f"Found file at: {found_path}")
                print(f"Disk Hash: {disk_hash}")
                print(f"Hash Match?: {disk_hash == art.content_hash}")
                print(f"Disk Size: {disk_size} (DB Size Match?: {disk_size == art.content_size_bytes})")
            else:
                print(f"WARNING: File NOT found in any candidate path! Storage path was {art.storage_path}")

    # 4. Compare unified diff in git with expected diff
    git_diff = subprocess.run(
        ["git", "-C", str(CANONICAL_REPO), "diff", f"{BASE_COMMIT}..{EXPECTED_COMMIT}"],
        capture_output=True, text=True, check=True
    ).stdout
    print(f"\nGit Diff between {BASE_COMMIT[:8]} and {EXPECTED_COMMIT[:8]}: {len(git_diff)} chars, {len(git_diff.splitlines())} lines")

if __name__ == "__main__":
    asyncio.run(run())
