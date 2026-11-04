from pathlib import Path

content = '''"""Reconcile schema drift and seed immutable system roles.

Revision ID: e7f8a9b0123c
Revises: d5e6f708192a
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "e7f8a9b0123c"
down_revision: Union[str, Sequence[str], None] = "d5e6f708192a"
branch_labels = None
depends_on = None

SYSTEM_ROLES = [
    {
        "role_id": "SUPER_ADMIN",
        "name": "Super Administrator",
        "description": "Workspace Owner with Full System Control and User Provisioning.",
        "permissions": [
            "artifact:download", "artifact:read", "audit:read",
            "gate:approve_g1", "gate:approve_g2", "gate:approve_g3", "gate:approve_g4", "gate:review",
            "job:cancel", "job:create", "job:intake", "job:pause_resume", "job:read",
            "settings:update", "user:manage"
        ],
    },
    {
        "role_id": "ADMIN",
        "name": "Workspace Administrator",
        "description": "Job Creator, Workspace Settings, and Approval Governance.",
        "permissions": [
            "artifact:download", "artifact:read", "audit:read",
            "gate:approve_g1", "gate:approve_g2", "gate:approve_g3", "gate:approve_g4", "gate:review",
            "job:cancel", "job:create", "job:intake", "job:pause_resume", "job:read",
            "settings:update"
        ],
    },
    {
        "role_id": "REVIEWER",
        "name": "Gate Reviewer",
        "description": "Authorized Human Approver for G1-G4 checkpoints and waiver signoff.",
        "permissions": [
            "artifact:download", "artifact:read", "audit:read",
            "gate:approve_g1", "gate:approve_g2", "gate:approve_g3", "gate:approve_g4", "gate:review",
            "job:pause_resume", "job:read"
        ],
    },
    {
        "role_id": "DEVELOPER",
        "name": "Platform Developer",
        "description": "Job Explorer, Artifact Inspector, and Code Verification Analyst.",
        "permissions": [
            "artifact:download", "artifact:read", "audit:read",
            "gate:review", "job:read"
        ],
    },
    {
        "role_id": "VIEWER",
        "name": "Read-Only Viewer",
        "description": "Read-Only inspection of modernization progress and public reports.",
        "permissions": [
            "artifact:read", "gate:review", "job:read"
        ],
    },
]

def upgrade() -> None:
    # 1. Reconcile drift on feasibility_reports index
    op.create_index(
        "ix_feasibility_reports_content_hash",
        "feasibility_reports",
        ["content_hash"],
        unique=False,
    )

    # 2. Reconcile drift on repository_inventories index naming
    op.drop_index("ix_repository_inventories_hash", table_name="repository_inventories")
    op.create_index(
        "ix_repository_inventories_inventory_hash",
        "repository_inventories",
        ["inventory_hash"],
        unique=False,
    )

    # 3. Seed immutable system roles idempotently
    roles_table = sa.table(
        "roles",
        sa.column("role_id", sa.String),
        sa.column("name", sa.String),
        sa.column("description", sa.String),
        sa.column("permissions", sa.JSON),
    )
    for role in SYSTEM_ROLES:
        stmt = postgresql.insert(roles_table).values(**role).on_conflict_do_nothing(index_elements=["role_id"])
        op.execute(stmt)


def downgrade() -> None:
    # Rollback index names
    op.drop_index("ix_repository_inventories_inventory_hash", table_name="repository_inventories")
    op.create_index("ix_repository_inventories_hash", "repository_inventories", ["inventory_hash"])
    op.drop_index("ix_feasibility_reports_content_hash", table_name="feasibility_reports")
'''

migration_path = Path("backend/alembic/versions/e7f8a9b0123c_reconcile_schema_drift_and_seed_roles.py")
migration_path.write_text(content, encoding="utf-8")
print(f"Updated {migration_path} with sa.JSON permissions.")
