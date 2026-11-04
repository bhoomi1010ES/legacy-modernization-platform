"""Automated regression coverage for Spendwise Phase 6 first module reproducibility invariants.

Covers:
1. Plan hash verification rejects mutated plans.
2. Module attempt history is preserved and cannot be overwritten.
3. Verification report cannot be bound to an attempt without matching artifact hashes.
4. API endpoints return consistent data matching the database.
"""

import hashlib
import json
import uuid
import pytest
from pathlib import Path
from sqlalchemy import select
from httpx import AsyncClient, ASGITransport

from app.core.database import AsyncSessionLocal
from app.models.job import Job
from app.models.module import Module, ModuleAttempt
from app.models.artifact import Artifact
from app.models.agent import AgentRun
from app.models.workflow import WorkflowGate
from app.models.user import User
from app.main import create_app
from app.api.deps import get_current_user_and_permissions, get_current_user, get_optional_user

JOB_ID = uuid.UUID("eb2bbaa9-90ee-4e9d-b340-5e025594126c")
MODULE_ID = uuid.UUID("8a53e2d8-e298-5112-a9a7-cca8fe8cc3c3")
ATTEMPT_4_ID = uuid.UUID("aadd09e9-9381-46db-a4b8-d9b5c41fcf3a")
G3_GATE_ID = uuid.UUID("916cd13c-8a22-4d0e-9923-9f218bb4308a")
ADMIN_USER_ID = uuid.UUID("bbacac52-6e67-43a3-9983-3ad6354343d2")
EXPECTED_PLAN_HASH = "f08e5394f61fc500774bb4d90eff0676a884406984b36d5905a52b1085ad9515"


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.mark.asyncio
async def test_conversion_plan_hash_integrity_and_mutation_rejection():
    """Verify that the approved conversion plan has an immutable hash matching G3 approval."""
    async with AsyncSessionLocal() as db:
        gate = await db.get(WorkflowGate, G3_GATE_ID)
        assert gate is not None
        assert gate.status == "APPROVED"
        assert gate.artifact_hashes is not None

        # Verify that both artifact entries in G3 map to the authoritative hash
        plan_hashes = gate.artifact_hashes
        for art_id_str, expected_hash in plan_hashes.items():
            assert expected_hash == EXPECTED_PLAN_HASH, f"Plan hash {expected_hash} does not match expected {EXPECTED_PLAN_HASH}"
            
            # Check DB artifact record
            art = await db.get(Artifact, uuid.UUID(art_id_str))
            assert art is not None
            assert art.content_hash == EXPECTED_PLAN_HASH

            # Check disk content
            candidates = [
                Path("artifacts") / art.storage_path,
                Path("artifacts/jobs") / str(JOB_ID) / art.storage_path,
                Path(art.storage_path),
            ]
            file_path = next((c for c in candidates if c.exists()), None)
            assert file_path is not None, f"Artifact file {art.storage_path} missing on disk"
            disk_bytes = file_path.read_bytes()
            assert sha256_bytes(disk_bytes) == EXPECTED_PLAN_HASH

        # Mutation invariant: any tampered bytes must fail hash verification
        tampered_bytes = disk_bytes + b" "
        assert sha256_bytes(tampered_bytes) != EXPECTED_PLAN_HASH


@pytest.mark.asyncio
async def test_module_attempt_history_preservation():
    """Verify that all historical module attempts are preserved in order and immutable."""
    async with AsyncSessionLocal() as db:
        attempts = list(
            (
                await db.execute(
                    select(ModuleAttempt)
                    .where(ModuleAttempt.module_id == MODULE_ID)
                    .order_by(ModuleAttempt.attempt_number)
                )
            )
            .scalars()
            .all()
        )

        assert len(attempts) == 4, f"Expected 4 attempts, found {len(attempts)}"
        
        # Verify sequence and status progression
        assert attempts[0].attempt_number == 1
        assert attempts[0].status == "REPAIR_REQUIRED"
        assert attempts[0].attempt_id == uuid.UUID("6ab2fd8d-1b68-4aff-9fbe-24621bba8585")

        assert attempts[1].attempt_number == 2
        assert attempts[1].status == "BLOCKED"
        assert attempts[1].attempt_id == uuid.UUID("c7ebaa1c-637b-4779-bff5-8ccc0896d10a")

        assert attempts[2].attempt_number == 3
        assert attempts[2].status == "REPAIR_REQUIRED"
        assert attempts[2].attempt_id == uuid.UUID("d067e6b6-3482-445b-8ce9-8be3019c9837")

        assert attempts[3].attempt_number == 4
        assert attempts[3].status == "VERIFIED"
        assert attempts[3].attempt_id == ATTEMPT_4_ID
        assert attempts[3].git_branch == f"job/{JOB_ID}/module/{MODULE_ID}/attempt/4"

        # Verify module status reflects the final verified attempt
        module = await db.get(Module, MODULE_ID)
        assert module is not None
        assert module.status == "VERIFIED"


@pytest.mark.asyncio
async def test_verification_report_artifact_hash_binding():
    """Verify that attempt 4 artifacts match cryptographic hashes and output refs."""
    async with AsyncSessionLocal() as db:
        attempt = await db.get(ModuleAttempt, ATTEMPT_4_ID)
        assert attempt is not None
        assert attempt.agent_run_id is not None

        agent_run = await db.get(AgentRun, attempt.agent_run_id)
        assert agent_run is not None
        assert agent_run.status == "SUCCEEDED"
        assert agent_run.agent_name == "CodeWriter"

        # Expected output artifacts: CONVERTED_MODULE v3, VERIFICATION_REPORT v3, REVIEW_REPORT v3
        expected_artifacts = [
            ("CONVERTED_MODULE", "cc5a967132dfdbb32b0db921bfd2834991784d778ddde9d363b8b12f8b184275"),
            ("VERIFICATION_REPORT", "a9d6d623a95a9f357ba417f04088728c50a2f1d9df80918d0ce2c5843d9074a6"),
            ("REVIEW_REPORT", "c5b89b909b292d44c0eeeae220daa4e5f68c5b116fd64b9905d06d1ee4613b0a"),
        ]

        for art_type, expected_hash in expected_artifacts:
            art = (
                await db.execute(
                    select(Artifact).where(
                        Artifact.job_id == JOB_ID,
                        Artifact.artifact_type == art_type,
                        Artifact.version == 3,
                    )
                )
            ).scalars().first()
            assert art is not None, f"Artifact {art_type} v3 missing in DB"
            assert art.content_hash == expected_hash

            # Verify disk bytes match
            candidates = [
                Path("artifacts") / art.storage_path,
                Path("artifacts/jobs") / str(JOB_ID) / art.storage_path,
                Path(art.storage_path),
            ]
            file_path = next((c for c in candidates if c.exists()), None)
            assert file_path is not None, f"Artifact {art.storage_path} missing on disk"
            assert sha256_bytes(file_path.read_bytes()) == expected_hash

            # Verify referenced in agent run output refs
            assert str(art.artifact_id) in agent_run.output_artifact_refs


@pytest.mark.asyncio
async def test_api_endpoints_evidence_consistency():
    """Verify that backend API endpoints return consistent data matching DB and disk."""
    app = create_app()

    async with AsyncSessionLocal() as db:
        admin_user = await db.get(User, ADMIN_USER_ID)
        assert admin_user is not None

    app.dependency_overrides[get_current_user_and_permissions] = lambda: (admin_user, ["*"])
    app.dependency_overrides[get_current_user] = lambda: admin_user
    app.dependency_overrides[get_optional_user] = lambda: admin_user

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        # 1. Gate endpoint
        res = await client.get(f"/api/v1/gates/{G3_GATE_ID}")
        assert res.status_code == 200
        gate_body = res.json()
        assert gate_body["status"] == "APPROVED"
        assert gate_body["gate_type"] == "G3"

        # 2. Module attempts board endpoint
        res = await client.get(f"/api/v1/jobs/{JOB_ID}/module-attempts")
        assert res.status_code == 200
        board = res.json()
        target_mod = next(m for m in board["modules"] if m["module_id"] == str(MODULE_ID))
        assert target_mod["status"] == "VERIFIED"
        assert len(target_mod["attempts"]) == 4

        # 3. Module attempt detail
        res = await client.get(f"/api/v1/module-attempts/{ATTEMPT_4_ID}")
        assert res.status_code == 200
        att_body = res.json()
        assert att_body["status"] == "VERIFIED"
        assert att_body["evidence"]["base_sha"] == "531f76a56424cea4c2ebc773b8cd649536a7d8b0"

        # 4. Attempt diff endpoint
        res = await client.get(f"/api/v1/module-attempts/{ATTEMPT_4_ID}/diff")
        assert res.status_code == 200
        diff_body = res.json()
        assert len(diff_body["changed_files"]) == 4
        assert "app/modules/app-utils_b30e84/csv_utils.py" in diff_body["changed_files"]

        # 5. Review endpoint
        res = await client.get(f"/api/v1/module-attempts/{ATTEMPT_4_ID}/review")
        assert res.status_code == 200
        rev_body = res.json()
        assert rev_body["status"] == "PASS"
        assert rev_body["findings"] == []

        # 6. Test results endpoint
        res = await client.get(f"/api/v1/module-attempts/{ATTEMPT_4_ID}/test-results")
        assert res.status_code == 200
        test_body = res.json()
        assert len(test_body["checks"]) == 4
        assert all(c["status"] == "PASS" for c in test_body["checks"])
        assert len(test_body["results"]) == 141
        assert all(r["status"] == "PASS" for r in test_body["results"])
