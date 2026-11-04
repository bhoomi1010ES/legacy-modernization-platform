"""Fix the two remaining W08 test failures:
1. test_replanning_invalidates_contract_changed_modules: Add target_stack and target_architecture to TargetBlueprint.
2. test_planner_coordinator_consumes_all_nine_prerequisites: Seed a RepositorySnapshot artifact before
   creating artifacts that reference snap_hash_001 in derived_from; also add target_stack/target_architecture to TargetBlueprint.
"""
import re

FILE = r"C:\Users\lenovo\Desktop\rebase\backend\tests\test_w08_planner_dag_and_scheduler.py"

with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

# =====================================================================
# FIX 1: test_replanning — first TargetBlueprint (bp, ~line 641)
# =====================================================================
old_bp_v1 = '''        bp = TargetBlueprint(
            job_id=str(job_id),
            version=1,
            components=[
                TargetComponent(
                    component_id="mod_core",
                    name="CoreComponent",
                    target_path="src/v1_core.py",
                    responsibilities=["Core"],
                    mapped_legacy_modules=["mod_1"],
                    interfaces=["ICoreV1"],
                    dependencies=[],
                )
            ],
            content_hash="bp_v1_hash",
        )'''

new_bp_v1 = '''        bp = TargetBlueprint(
            job_id=str(job_id),
            version=1,
            target_stack="FastAPI",
            target_architecture="modular-monolith",
            components=[
                TargetComponent(
                    component_id="mod_core",
                    name="CoreComponent",
                    target_path="src/v1_core.py",
                    responsibilities=["Core"],
                    mapped_legacy_modules=["mod_1"],
                    interfaces=["ICoreV1"],
                    dependencies=[],
                )
            ],
            content_hash="bp_v1_hash",
        )'''

assert old_bp_v1 in content, "Could not find bp_v1 pattern"
content = content.replace(old_bp_v1, new_bp_v1, 1)
print("FIX 1a: Added target_stack/target_architecture to bp (replanning v1)")

# FIX 1b: second TargetBlueprint (bp_v2, ~line 691)
old_bp_v2 = '''        bp_v2 = TargetBlueprint(
            job_id=str(job_id),
            version=2,
            components=[
                TargetComponent(
                    component_id="mod_core",
                    name="CoreComponent",
                    target_path="src/v2_core.py",  # Changed!
                    responsibilities=["Core v2"],
                    mapped_legacy_modules=["mod_1"],
                    interfaces=["ICoreV2"],        # Changed!
                    dependencies=[],
                )
            ],
            content_hash="bp_v2_hash",
        )'''

new_bp_v2 = '''        bp_v2 = TargetBlueprint(
            job_id=str(job_id),
            version=2,
            target_stack="FastAPI",
            target_architecture="modular-monolith",
            components=[
                TargetComponent(
                    component_id="mod_core",
                    name="CoreComponent",
                    target_path="src/v2_core.py",  # Changed!
                    responsibilities=["Core v2"],
                    mapped_legacy_modules=["mod_1"],
                    interfaces=["ICoreV2"],        # Changed!
                    dependencies=[],
                )
            ],
            content_hash="bp_v2_hash",
        )'''

assert old_bp_v2 in content, "Could not find bp_v2 pattern"
content = content.replace(old_bp_v2, new_bp_v2, 1)
print("FIX 1b: Added target_stack/target_architecture to bp_v2 (replanning v2)")

# =====================================================================
# FIX 2: test_planner_coordinator_consumes_all_nine_prerequisites
#   - Add a RepositorySnapshot artifact BEFORE the CHARACTERIZATION_SUITE
#     so that derived_from=["snap_hash_001"] resolves.
#   - Add target_stack/target_architecture to the TargetBlueprint.
# =====================================================================

# 2a: Seed a RepositorySnapshot artifact right after adding snap to session
old_seed_char = '''        # Seed CharacterizationSuite artifact
        await artifact_service.create_artifact(
            db=db,
            job_id=job.job_id,
            artifact_type="CHARACTERIZATION_SUITE",
            version=1,
            content_bytes=json.dumps({"suite": "verified", "coverage": {"pct": 92.5}}).encode("utf-8"),
            producing_agent="CharacterizerAgent",
            derived_from=["snap_hash_001"],
            commit=True,
        )'''

new_seed_char = '''        # Seed RepositorySnapshot artifact so derived_from references resolve
        await artifact_service.create_artifact(
            db=db,
            job_id=job.job_id,
            artifact_type="RepositorySnapshot",
            version=1,
            content_bytes=json.dumps({"snapshot": True}).encode("utf-8"),
            content_hash="snap_hash_001",
            producing_agent="IntakeAgent",
            derived_from=[],
            commit=True,
        )

        # Seed CharacterizationSuite artifact
        await artifact_service.create_artifact(
            db=db,
            job_id=job.job_id,
            artifact_type="CHARACTERIZATION_SUITE",
            version=1,
            content_bytes=json.dumps({"suite": "verified", "coverage": {"pct": 92.5}}).encode("utf-8"),
            producing_agent="CharacterizerAgent",
            derived_from=["snap_hash_001"],
            commit=True,
        )'''

assert old_seed_char in content, "Could not find CHARACTERIZATION_SUITE seed pattern"
content = content.replace(old_seed_char, new_seed_char, 1)
print("FIX 2a: Seeded RepositorySnapshot artifact before CHARACTERIZATION_SUITE")

# 2b: Add target_stack/target_architecture to TargetBlueprint in test 10
old_bp_nine = '''        bp = TargetBlueprint(
            job_id=str(job.job_id),
            version=1,
            components=[
                TargetComponent(
                    component_id="comp_app",
                    name="ApplicationComponent",
                    target_path="app.py",
                    responsibilities=["App"],
                    mapped_legacy_modules=["mod_app"],
                    interfaces=[],
                    dependencies=[],
                )
            ],
            content_hash="bp_hash_001",
        )'''

new_bp_nine = '''        bp = TargetBlueprint(
            job_id=str(job.job_id),
            version=1,
            target_stack="FastAPI",
            target_architecture="modular-monolith",
            components=[
                TargetComponent(
                    component_id="comp_app",
                    name="ApplicationComponent",
                    target_path="app.py",
                    responsibilities=["App"],
                    mapped_legacy_modules=["mod_app"],
                    interfaces=[],
                    dependencies=[],
                )
            ],
            content_hash="bp_hash_001",
        )'''

assert old_bp_nine in content, "Could not find bp (nine-inputs) pattern"
content = content.replace(old_bp_nine, new_bp_nine, 1)
print("FIX 2b: Added target_stack/target_architecture to bp (nine-inputs)")

with open(FILE, "w", encoding="utf-8") as f:
    f.write(content)

print("\nAll fixes applied successfully.")

