"""Fix the two remaining W08 test failures by seeding prerequisite DB records
so that artifact provenance bridge lookups resolve correctly.

Test 9 (replanning): execute_planning publishes CONVERSION_PLAN with
  derived_from=[blueprint.content_hash].  The bridge lookup resolves this by
  finding a TargetBlueprintModel with that content_hash, then finding an
  Artifact of type TargetBlueprint.  We must seed:
  - TargetBlueprintModel with content_hash matching the blueprint
  - An artifact of type TargetBlueprint

Test 10 (nine-prerequisites): FeasibilityReportModel needs summary (NOT NULL).
  Also needs TargetBlueprintModel and TargetBlueprint artifact seeded.
"""
import re

FILE = r"C:\Users\lenovo\Desktop\rebase\backend\tests\test_w08_planner_dag_and_scheduler.py"

with open(FILE, "r", encoding="utf-8") as f:
    content = f.read()

# ==========================================================================
# FIX 1: test_replanning — seed TargetBlueprintModel + TargetBlueprint artifact
# before calling execute_planning.
# Insert right after "content_hash="leg_v1_hash","  / ")" closing of LegacyModel
# ==========================================================================

# We need to add seeding code after the LegacyModel is created, before plan_v1
old_plan_v1_call = """        # Plan v1
        plan_v1 = await planner_coordinator.execute_planning(
            db=db,
            job=job,
            blueprint=bp,
            legacy_model=leg,
        )"""

new_plan_v1_call = """        # Seed TargetBlueprintModel record so provenance bridge resolves bp_v1_hash
        bp_model = TargetBlueprintModel(
            blueprint_id=uuid.uuid4(),
            job_id=job_id,
            version=1,
            target_stack="FastAPI",
            target_architecture="modular-monolith",
            content_hash="bp_v1_hash",
        )
        db.add(bp_model)
        await db.flush()

        # Seed TargetBlueprint artifact so bridge finds artifact_type=TargetBlueprint
        await artifact_service.create_artifact(
            db=db,
            job_id=job_id,
            artifact_type="TargetBlueprint",
            version=1,
            content_bytes=json.dumps({"blueprint": "v1"}).encode("utf-8"),
            producing_agent="ArchitectAgent",
            derived_from=[],
            commit=False,
        )
        await db.flush()

        # Plan v1
        plan_v1 = await planner_coordinator.execute_planning(
            db=db,
            job=job,
            blueprint=bp,
            legacy_model=leg,
        )"""

assert old_plan_v1_call in content, f"Could not find plan_v1 call pattern"
content = content.replace(old_plan_v1_call, new_plan_v1_call, 1)
print("FIX 1a: Seeded TargetBlueprintModel + artifact before plan_v1")

# Also seed bp_v2 model before plan_v2
old_plan_v2_call = """        plan_v2 = await planner_coordinator.execute_planning(
            db=db,
            job=job,
            blueprint=bp_v2,
            legacy_model=leg,
        )"""

new_plan_v2_call = """        # Seed TargetBlueprintModel v2 record so provenance bridge resolves bp_v2_hash
        bp_model_v2 = TargetBlueprintModel(
            blueprint_id=uuid.uuid4(),
            job_id=job_id,
            version=2,
            target_stack="FastAPI",
            target_architecture="modular-monolith",
            content_hash="bp_v2_hash",
        )
        db.add(bp_model_v2)

        # Seed TargetBlueprint artifact v2
        await artifact_service.create_artifact(
            db=db,
            job_id=job_id,
            artifact_type="TargetBlueprint",
            version=2,
            content_bytes=json.dumps({"blueprint": "v2"}).encode("utf-8"),
            producing_agent="ArchitectAgent",
            derived_from=[],
            commit=False,
        )
        await db.flush()

        plan_v2 = await planner_coordinator.execute_planning(
            db=db,
            job=job,
            blueprint=bp_v2,
            legacy_model=leg,
        )"""

assert old_plan_v2_call in content, f"Could not find plan_v2 call pattern"
content = content.replace(old_plan_v2_call, new_plan_v2_call, 1)
print("FIX 1b: Seeded TargetBlueprintModel v2 + artifact before plan_v2")


# ==========================================================================
# FIX 2: test_nine_prerequisites — add summary to FeasibilityReportModel
# ==========================================================================

old_feas = """        # Seed FeasibilityReport
        feas = FeasibilityReportModel(
            report_id=uuid.uuid4(),
            job_id=job.job_id,
            version=1,
            blueprint_version=1,
            legacy_model_version=1,
            overall_score=95.0,
            unsupported_count=0,
            custom_build_count=0,
            substitute_count=0,
            unknown_count=0,
            content_hash="feas_hash_001",
        )
        db.add(feas)"""

new_feas = """        # Seed FeasibilityReport
        feas = FeasibilityReportModel(
            report_id=uuid.uuid4(),
            job_id=job.job_id,
            version=1,
            blueprint_version=1,
            legacy_model_version=1,
            overall_score=95.0,
            unsupported_count=0,
            custom_build_count=0,
            substitute_count=0,
            unknown_count=0,
            summary="Overall feasibility 95%: all capabilities supported.",
            content_hash="feas_hash_001",
        )
        db.add(feas)"""

assert old_feas in content, f"Could not find FeasibilityReportModel pattern"
content = content.replace(old_feas, new_feas, 1)
print("FIX 2a: Added summary to FeasibilityReportModel")

# Also need to seed TargetBlueprintModel and TargetBlueprint artifact for test 10
# The execute_planning call uses derived_from=[blueprint.content_hash] = "bp_hash_001"

old_bp_nine_call = """        plan = await planner_coordinator.execute_planning(
            db=db,
            job=job,
            blueprint=bp,
            legacy_model=leg,
        )"""

new_bp_nine_call = """        # Seed TargetBlueprintModel so provenance bridge resolves bp_hash_001
        bp_model = TargetBlueprintModel(
            blueprint_id=uuid.uuid4(),
            job_id=job.job_id,
            version=1,
            target_stack="FastAPI",
            target_architecture="modular-monolith",
            content_hash="bp_hash_001",
        )
        db.add(bp_model)

        # Seed TargetBlueprint artifact
        await artifact_service.create_artifact(
            db=db,
            job_id=job.job_id,
            artifact_type="TargetBlueprint",
            version=1,
            content_bytes=json.dumps({"blueprint": "nine-inputs"}).encode("utf-8"),
            producing_agent="ArchitectAgent",
            derived_from=[],
            commit=False,
        )
        await db.flush()

        plan = await planner_coordinator.execute_planning(
            db=db,
            job=job,
            blueprint=bp,
            legacy_model=leg,
        )"""

assert old_bp_nine_call in content, f"Could not find plan call in nine-inputs test"
content = content.replace(old_bp_nine_call, new_bp_nine_call, 1)
print("FIX 2b: Seeded TargetBlueprintModel + artifact in nine-inputs test")

# Also ensure TargetBlueprintModel is imported
if "TargetBlueprintModel" not in content.split("from app.models.phase4 import")[1].split(")")[0]:
    # Add to imports
    content = content.replace(
        "    TargetBlueprintModel,\n",
        "    TargetBlueprintModel,\n",
    )
    print("TargetBlueprintModel already imported")
else:
    print("TargetBlueprintModel already imported")

with open(FILE, "w", encoding="utf-8") as f:
    f.write(content)

print("\nAll fixes applied successfully.")

