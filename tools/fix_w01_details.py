from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# 1. Update jobs.py imports
jobs_path = ROOT / "backend" / "app" / "api" / "v1" / "jobs.py"
jobs_text = jobs_path.read_text(encoding="utf-8")

old_import = "from app.core.errors import ErrorDetail, NotFoundException, ValidationException"
new_import = "from app.core.errors import ErrorDetail, ForbiddenException, NotFoundException, ValidationException\nfrom app.core.config import settings\nfrom app.services.git_adapter import ControlledGitAdapter, GitSecurityException"

if "from app.core.config import settings" not in jobs_text:
    jobs_text = jobs_text.replace(old_import, new_import)
    jobs_path.write_text(jobs_text, encoding="utf-8")
    print("Added missing imports to jobs.py")

# 2. Update schemas/auth.py
schemas_path = ROOT / "backend" / "app" / "schemas" / "auth.py"
schemas_text = schemas_path.read_text(encoding="utf-8")

old_schema = """class RoleAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(..., description="Target role to assign (e.g. REVIEWER, ADMIN, DEVELOPER, VIEWER).")"""

new_schema = """class RoleAssignmentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role: str = Field(..., description="Target role to assign (e.g. REVIEWER, ADMIN, DEVELOPER, VIEWER).")
    reason: Optional[str] = Field(None, description="Audit rationale for the role change.")"""

if "reason: Optional[str]" not in schemas_text:
    schemas_text = schemas_text.replace(old_schema, new_schema)
    schemas_path.write_text(schemas_text, encoding="utf-8")
    print("Updated RoleAssignmentRequest with optional reason field")

# 3. Update test_w01_security.py gate endpoint URL
test_path = ROOT / "backend" / "tests" / "test_w01_security.py"
test_text = test_path.read_text(encoding="utf-8")

test_text = test_text.replace(
    'f"/api/v1/jobs/{job_id}/gates/{gate_id}/decision"',
    'f"/api/v1/jobs/{job_id}/gates/{gate_id}/decisions"'
)
test_path.write_text(test_text, encoding="utf-8")
print("Updated test_w01_security.py endpoint URLs")

