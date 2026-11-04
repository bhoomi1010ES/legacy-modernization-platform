"""Bind module work to the approved plan snapshot and backfill normalized edges.

Revision ID: c5d6e7f8091a
Revises: b3c4d5e6f7a8
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "c5d6e7f8091a"
down_revision: Union[str, Sequence[str], None] = "b3c4d5e6f7a8"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("modules", sa.Column("plan_hash", sa.String(128), nullable=True))
    op.add_column("modules", sa.Column("upstream_approval_hashes", sa.JSON(), server_default="{}", nullable=False))
    op.add_column("modules", sa.Column("integration_base_sha", sa.String(64), nullable=True))
    op.create_index("ix_modules_plan_hash", "modules", ["plan_hash"])
    op.add_column("module_attempts", sa.Column("worker_id", sa.String(100), nullable=True))
    op.create_index("ix_module_attempts_worker_id", "module_attempts", ["worker_id"])
    # Preserve legacy JSON edges before the scheduler enforces graph consistency.
    op.execute(sa.text("""
        INSERT INTO module_dependencies (dependency_id, job_id, parent_id, child_id, created_at)
        SELECT gen_random_uuid(), child.job_id, parent.module_id, child.module_id, now()
        FROM modules AS child
        CROSS JOIN LATERAL jsonb_array_elements_text(CAST(child.dependency_module_ids AS jsonb)) AS edge(parent_id)
        JOIN modules AS parent ON parent.module_id::text = edge.parent_id
                              AND parent.job_id = child.job_id
        ON CONFLICT (parent_id, child_id) DO NOTHING
    """))


def downgrade() -> None:
    op.drop_index("ix_module_attempts_worker_id", table_name="module_attempts")
    op.drop_column("module_attempts", "worker_id")
    op.drop_index("ix_modules_plan_hash", table_name="modules")
    op.drop_column("modules", "integration_base_sha")
    op.drop_column("modules", "upstream_approval_hashes")
    op.drop_column("modules", "plan_hash")
