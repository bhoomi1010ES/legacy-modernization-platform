import json
"""Export converted code and projects into dedicated workspace folders."""

import argparse
import asyncio
import os
import re
import shutil
import subprocess
import sys
import uuid
from pathlib import Path

# Add backend to path
ROOT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT_DIR / "backend"))

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.module import Module
from app.models.artifact import Artifact
from sqlalchemy import select


def sanitize_filename(name: str) -> str:
    s = re.sub(r"[^\w\s-]", "", name).strip().lower()
    return re.sub(r"[-\s]+", "-", s)


async def export_job(job_id_str: str, output_base: Path = None):
    output_base = output_base or (ROOT_DIR / "converted_projects")
    job_id = uuid.UUID(job_id_str)
    
    async with AsyncSessionLocal() as db:
        job = await db.get(Job, job_id)
        if not job:
            print(f"Error: Job {job_id} not found.")
            return

        slug = sanitize_filename(job.name) or str(job.job_id)[:8]
        dest_dir = output_base / slug
        dest_dir.mkdir(parents=True, exist_ok=True)
        
        print(f"\n================================================================================")
        print(f"  EXPORTING CONVERTED CODE FOR: {job.name}")
        print(f"  Target Destination: {dest_dir}")
        print(f"================================================================================")

        # 1. Check if git repository workspace exists with an integration branch
        ws_dir = ROOT_DIR / "repo_workspaces" / f"job_{job.job_id}"
        exported_from_git = False
        
        if ws_dir.exists() and (ws_dir / ".git").exists():
            branches_to_try = []
            if job.integration_branch:
                branches_to_try.append(job.integration_branch)
            
            # Find any integration branches
            res = subprocess.run(["git", "-C", str(ws_dir), "branch", "--list", "*integration*"], capture_output=True, text=True)
            for line in res.stdout.splitlines():
                b = line.replace("*", "").strip()
                if b and b not in branches_to_try:
                    branches_to_try.append(b)

            for branch in branches_to_try:
                print(f"Checking Git branch: {branch}...")
                # Export archive from branch directly to dest_dir
                archive_cmd = subprocess.run(["git", "-C", str(ws_dir), "archive", branch], capture_output=True)
                if archive_cmd.returncode == 0 and archive_cmd.stdout:
                    import tarfile
                    import io
                    with tarfile.open(fileobj=io.BytesIO(archive_cmd.stdout)) as tar:
                        tar.extractall(path=dest_dir)
                    print(f"  Successfully extracted full integrated branch '{branch}' -> {dest_dir}")
                    exported_from_git = True
                    break

        # 2. Also extract individual CONVERTED_MODULE artifacts
        artifacts = (
            await db.execute(
                select(Artifact)
                .where(Artifact.job_id == job_id, Artifact.artifact_type == "CONVERTED_MODULE")
                .order_by(Artifact.version.asc())
            )
        ).scalars().all()

        modules_dest = dest_dir / "converted_modules_only"
        modules_dest.mkdir(parents=True, exist_ok=True)
        
        file_count = 0
        for art in artifacts:
            art_file = ROOT_DIR / art.storage_path
            if not art_file.exists():
                art_file = ROOT_DIR / "backend" / art.storage_path
            
            if art_file.exists():
                try:
                    payload = json.loads(art_file.read_text(encoding="utf-8"))
                    files = payload.get("files", {})
                    for rel_path, content in files.items():
                        target_file = dest_dir / rel_path
                        target_file.parent.mkdir(parents=True, exist_ok=True)
                        target_file.write_text(content, encoding="utf-8")

                        mod_only_file = modules_dest / Path(rel_path).name
                        mod_only_file.write_text(content, encoding="utf-8")
                        
                        print(f"  Exported converted source file: {rel_path} ({len(content)} chars)")
                        file_count += 1
                except Exception as e:
                    print(f"  Warning reading artifact {art_file}: {e}")

        # Write modernization metadata receipt
        receipt = {
            "job_id": str(job.job_id),
            "job_name": job.name,
            "source_repository": job.source_repository,
            "source_revision": job.source_revision,
            "source_stack": job.source_stack,
            "target_stack": job.target_stack,
            "status": job.status,
            "exported_files_count": file_count,
        }
        (dest_dir / "MODERNIZATION_RECEIPT.json").write_text(json.dumps(receipt, indent=2), encoding="utf-8")
        
        print(f"\nSUCCESS! Converted code exported to: {dest_dir.resolve()}")


async def main():
    parser = argparse.ArgumentParser(description="Export converted code to dedicated folder")
    parser.add_argument("--job-id", type=str, default="399f0951-ffa7-4119-b514-939f8ae1bcc9", help="Job ID to export")
    args = parser.parse_args()
    await export_job(args.job_id)


if __name__ == "__main__":
    asyncio.run(main())
