"""Update PlanningContext in backend/app/schemas/phase4.py for W08."""

from pathlib import Path

FILE_PATH = Path("backend/app/schemas/phase4.py")
content = FILE_PATH.read_text(encoding="utf-8")

# 1. Add Decimal import if not present
if "from decimal import Decimal" not in content:
    content = "from decimal import Decimal\n" + content

# 2. Update PlanningContext
old_ctx = """class PlanningContext(BaseModel):
    \"\"\"Authoritative input context feeding ModulePlanner and PlanAggregator.\"\"\"
    job_id: str
    legacy_model: LegacyModel
    target_blueprint: TargetBlueprint
    feasibility_report: Optional[FeasibilityReport] = None
    g1_decisions: List[G1DecisionRecord] = Field(default_factory=list)
    characterization_suite: Optional[Dict[str, Any]] = None
    characterization_coverage: Optional[Dict[str, Any]] = None
    schema_data_plan: Optional[Dict[str, Any]] = None
    provenance_hashes: Dict[str, str] = Field(default_factory=dict)
    model_config = ConfigDict(extra="forbid")"""

new_ctx = """class PlanningContext(BaseModel):
    \"\"\"Authoritative input context feeding ModulePlanner and PlanAggregator.\"\"\"
    job_id: str
    legacy_model: LegacyModel
    target_blueprint: TargetBlueprint
    feasibility_report: Optional[FeasibilityReport] = None
    g1_decisions: List[G1DecisionRecord] = Field(default_factory=list)
    characterization_suite: Optional[Dict[str, Any]] = None
    characterization_coverage: Optional[Dict[str, Any]] = None
    schema_data_plan: Optional[Dict[str, Any]] = None
    provenance_hashes: Dict[str, str] = Field(default_factory=dict)
    stack_profile: Optional[Dict[str, Any]] = None
    cost_ceiling_usd: Optional[Decimal] = None
    baseline_source_sha: Optional[str] = None
    model_config = ConfigDict(extra="forbid")"""

assert old_ctx in content, "old_ctx not found in phase4.py"
content = content.replace(old_ctx, new_ctx, 1)

FILE_PATH.write_text(content, encoding="utf-8")
print("Successfully patched PlanningContext in backend/app/schemas/phase4.py")

