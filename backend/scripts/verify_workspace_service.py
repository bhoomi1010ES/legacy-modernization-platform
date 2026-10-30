import asyncio
import sys
import uuid
from pathlib import Path

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.repository_workspace_service import RepositoryWorkspaceService

async def main():
    job_id = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
    service = RepositoryWorkspaceService()

    try:
        status = await service.validate_workspace(job_id)
        print("validate_workspace SUCCESS!")
        print(f"is_ready: {status.is_ready}")
        print(f"head_commit: {status.head_commit}")
        print(f"branch: {status.branch}")
        print(f"dirty: {status.dirty}")
        print(f"error_code: {status.error_code}")
        print(f"error_message: {status.error_message}")
    except Exception as e:
        print(f"validate_workspace FAILED: {type(e).__name__}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
