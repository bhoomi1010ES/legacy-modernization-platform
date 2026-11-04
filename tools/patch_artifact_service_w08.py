"""Update ArtifactService for W08 canonical artifact type normalization."""

from pathlib import Path

FILE_PATH = Path("backend/app/services/artifact_service.py")

content = FILE_PATH.read_text(encoding="utf-8")

# 1. Update import
old_import = "from app.models.artifact import Artifact, ArtifactDependency"
new_import = "from app.models.artifact import Artifact, ArtifactDependency, ArtifactType, normalize_artifact_type"
assert old_import in content, "old_import not found"
content = content.replace(old_import, new_import, 1)

# 2. Update publish_artifact to use canonical_type
old_pub = """        # 1. Server-side privilege check: Verifier spoofing prevention (SEC-07)
        normalized_type = "".join(ch for ch in artifact_type.upper() if ch.isalnum())
        if normalized_type in VERIFICATION_ARTIFACT_TYPES:
            agent_lower = (producing_agent or "").lower()
            if not ("verifier" in agent_lower or "verification" in agent_lower):
                raise ForbiddenException(
                    f"Only Verifier agents are authorized to publish verification evidence (attempted by '{producing_agent}')."
                )

        # 2. Enforce uniqueness: an existing version must never be overwritten
        stmt = select(Artifact).where(
            Artifact.job_id == job_id,
            Artifact.artifact_type == artifact_type,
            Artifact.version == version,
        )
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            raise ConflictException(
                f"Artifact '{artifact_type}' version {version} already exists for this job. Artifacts are strictly immutable."
            )"""

new_pub = """        canonical_type = normalize_artifact_type(artifact_type)

        # 1. Server-side privilege check: Verifier spoofing prevention (SEC-07)
        normalized_type = "".join(ch for ch in canonical_type.upper() if ch.isalnum())
        if normalized_type in VERIFICATION_ARTIFACT_TYPES:
            agent_lower = (producing_agent or "").lower()
            if not ("verifier" in agent_lower or "verification" in agent_lower):
                raise ForbiddenException(
                    f"Only Verifier agents are authorized to publish verification evidence (attempted by '{producing_agent}')."
                )

        # 2. Enforce uniqueness: an existing version must never be overwritten
        stmt = select(Artifact).where(
            Artifact.job_id == job_id,
            Artifact.artifact_type == canonical_type,
            Artifact.version == version,
        )
        res = await db.execute(stmt)
        if res.scalar_one_or_none():
            raise ConflictException(
                f"Artifact '{canonical_type}' version {version} already exists for this job. Artifacts are strictly immutable."
            )"""

assert old_pub in content, "old_pub not found"
content = content.replace(old_pub, new_pub, 1)

# 3. Update storage key and model creation
old_key = 'final_storage_key = f"jobs/{job_id}/artifacts/{artifact_type}_v{version}_{content_hash[:16]}.json"'
new_key = 'final_storage_key = f"jobs/{job_id}/artifacts/{canonical_type}_v{version}_{content_hash[:16]}.json"'
assert old_key in content, "old_key not found"
content = content.replace(old_key, new_key, 1)

old_model = """        artifact = Artifact(
            artifact_id=artifact_id,
            job_id=job_id,
            module_id=module_id,
            artifact_type=artifact_type,"""

new_model = """        artifact = Artifact(
            artifact_id=artifact_id,
            job_id=job_id,
            module_id=module_id,
            artifact_type=canonical_type,"""

assert old_model in content, "old_model not found"
content = content.replace(old_model, new_model, 1)

# 4. Update audit payload
old_audit = '"artifact_type": artifact_type,'
new_audit = '"artifact_type": canonical_type,'
content = content.replace(old_audit, new_audit)

# 5. Update list_artifacts
old_list = """        if artifact_type:
            query = query.where(Artifact.artifact_type == artifact_type)"""

new_list = """        if artifact_type:
            canonical_type = normalize_artifact_type(artifact_type)
            query = query.where(Artifact.artifact_type.in_([canonical_type, artifact_type]))"""

assert old_list in content, "old_list not found"
content = content.replace(old_list, new_list, 1)

FILE_PATH.write_text(content, encoding="utf-8")
print("Successfully patched artifact_service.py")

