import asyncio
import json
import sys
import uuid
from pathlib import Path
from httpx import AsyncClient, ASGITransport

sys.path.insert(0, str(Path("backend").resolve()))

from app.main import create_app
from app.core.database import AsyncSessionLocal
from app.models.user import User

JOB_ID = "eb2bbaa9-90ee-4e9d-b340-5e025594126c"
MODULE_ID = "8a53e2d8-e298-5112-a9a7-cca8fe8cc3c3"
ATTEMPT_ID = "aadd09e9-9381-46db-a4b8-d9b5c41fcf3a"
GATE_ID = "916cd13c-8a22-4d0e-9923-9f218bb4308a"

async def run():
    print("="*80)
    print("TASK F: AUDIT BACKEND API EVIDENCE INTEGRITY")
    print("="*80)

    app = create_app()

    # Get admin user for auth header/token
    async with AsyncSessionLocal() as db:
        admin_user = await db.get(User, uuid.UUID("bbacac52-6e67-43a3-9983-3ad6354343d2"))
        print(f"Auth user: {admin_user.email} (Role: {admin_user.role})")

    from app.api.deps import get_current_user_and_permissions, get_current_user, get_optional_user
    app.dependency_overrides[get_current_user_and_permissions] = lambda: (admin_user, ["*"])
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_optional_user] = lambda: admin_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. GET /api/v1/gates/{gate_id}
        res = await client.get(f"/api/v1/gates/{GATE_ID}")
        print(f"\n1. GET /api/v1/gates/{GATE_ID}")
        print(f"   Status Code: {res.status_code}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        gate_body = res.json()
        print(f"   Gate Type: {gate_body.get('gate_type')}")
        print(f"   Gate Status: {gate_body.get('status')}")
        print(f"   Artifact Hashes: {gate_body.get('artifact_hashes')}")

        # 2. GET /api/v1/jobs/{job_id}/module-attempts
        res = await client.get(f"/api/v1/jobs/{JOB_ID}/module-attempts")
        print(f"\n2. GET /api/v1/jobs/{JOB_ID}/module-attempts")
        print(f"   Status Code: {res.status_code}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        board_data = res.json()
        modules = board_data.get("modules", [])
        items = board_data.get("items", [])
        print(f"   Modules count on board: {len(modules)}")
        print(f"   Total attempt items: {len(items)}")
        target_mod = next((m for m in modules if m.get("module_id") == MODULE_ID or m.get("name") == "comp_app-utils_b30e84"), None)
        assert target_mod is not None, "Target module not found on board!"
        print(f"   Target Module Name: {target_mod.get('name')}")
        print(f"   Target Module Status: {target_mod.get('status')}")
        print(f"   Target Module Attempts count: {len(target_mod.get('attempts', []))}")
        for att in target_mod.get('attempts', []):
            print(f"     Attempt #{att.get('attempt_number')}: ID={att.get('attempt_id')}, Status={att.get('status')}")

        # 3. GET /api/v1/module-attempts/{attempt_id}
        res = await client.get(f"/api/v1/module-attempts/{ATTEMPT_ID}")
        print(f"\n3. GET /api/v1/module-attempts/{ATTEMPT_ID}")
        print(f"   Status Code: {res.status_code}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        att_detail = res.json()
        print(f"   Attempt Status: {att_detail.get('status')}")
        print(f"   Git Branch: {att_detail.get('git_branch')}")
        print(f"   Commit Hash: {att_detail.get('commit_hash')}")
        print(f"   Evidence keys: {list(att_detail.get('evidence', {}).keys())}")

        # 4. GET /api/v1/module-attempts/{attempt_id}/diff
        res = await client.get(f"/api/v1/module-attempts/{ATTEMPT_ID}/diff")
        print(f"\n4. GET /api/v1/module-attempts/{ATTEMPT_ID}/diff")
        print(f"   Status Code: {res.status_code}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        diff_detail = res.json()
        diff_str = diff_detail.get('diff', '')
        changed_files = diff_detail.get('changed_files', [])
        print(f"   Diff Content Length: {len(diff_str)} chars")
        print(f"   Changed Files ({len(changed_files)}): {changed_files}")

        # 5. GET /api/v1/module-attempts/{attempt_id}/review
        res = await client.get(f"/api/v1/module-attempts/{ATTEMPT_ID}/review")
        print(f"\n5. GET /api/v1/module-attempts/{ATTEMPT_ID}/review")
        print(f"   Status Code: {res.status_code}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        rev_detail = res.json()
        print(f"   Review Status: {rev_detail.get('status')}")
        print(f"   Findings: {rev_detail.get('findings')}")
        print(f"   Reviewer Version: {rev_detail.get('reviewer_version')}")

        # 6. GET /api/v1/module-attempts/{attempt_id}/test-results
        res = await client.get(f"/api/v1/module-attempts/{ATTEMPT_ID}/test-results")
        print(f"\n6. GET /api/v1/module-attempts/{ATTEMPT_ID}/test-results")
        print(f"   Status Code: {res.status_code}")
        assert res.status_code == 200, f"Expected 200, got {res.status_code}"
        test_detail = res.json()
        checks = test_detail.get('checks', [])
        results = test_detail.get('results', [])
        print(f"   Checks count: {len(checks)}")
        print(f"   Test results/cases count: {len(results)}")
        if checks:
            print(f"   Checks statuses: {[c.get('status') for c in checks]}")
        if results:
            print(f"   Cases passed count: {sum(1 for r in results if r.get('status') == 'PASS')}/{len(results)}")

if __name__ == "__main__":
    asyncio.run(run())
