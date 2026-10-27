"""Authoritative workflow identity, canonical phase and fenced leases.

Revision ID: d5e6f708192a
Revises: c4d5e6f70819
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d5e6f708192a"
down_revision: Union[str, Sequence[str], None] = "c4d5e6f70819"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("jobs", sa.Column("workflow_id", sa.Uuid(), nullable=True))
    op.execute("UPDATE jobs SET workflow_id = job_id WHERE workflow_id IS NULL")
    op.alter_column("jobs", "workflow_id", nullable=False)
    op.create_index("ix_jobs_workflow_id", "jobs", ["workflow_id"], unique=True)
    op.add_column("jobs", sa.Column("workflow_phase", sa.String(length=50), nullable=False, server_default="INTAKE"))
    op.create_index("ix_jobs_workflow_phase", "jobs", ["workflow_phase"], unique=False)
    op.create_check_constraint(
        "chk_job_workflow_phase",
        "jobs",
        "workflow_phase IN ('INTAKE','G1','CHARACTERIZATION','SCHEMA_DATA','G2','PLANNING','G3','CONVERSION','VERIFICATION','INTEGRATION','G4','COMPLETED','FAILED','CANCELLED')",
    )
    op.add_column("jobs", sa.Column("last_transition", sa.String(length=100), nullable=True))
    op.add_column("jobs", sa.Column("terminal_reason", sa.Text(), nullable=True))
    op.add_column("jobs", sa.Column("orchestration_owner", sa.String(length=255), nullable=True))
    op.add_column("jobs", sa.Column("orchestration_lease_expires_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("orchestration_generation", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("modules", sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"))
    op.add_column("modules", sa.Column("lease_heartbeat_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("module_attempts", sa.Column("lease_generation", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("module_attempts", "lease_generation")
    op.drop_column("modules", "lease_heartbeat_at")
    op.drop_column("modules", "lease_generation")
    op.drop_column("jobs", "orchestration_generation")
    op.drop_column("jobs", "orchestration_lease_expires_at")
    op.drop_column("jobs", "orchestration_owner")
    op.drop_column("jobs", "terminal_reason")
    op.drop_column("jobs", "last_transition")
    op.drop_constraint("chk_job_workflow_phase", "jobs", type_="check")
    op.drop_index("ix_jobs_workflow_phase", table_name="jobs")
    op.drop_column("jobs", "workflow_phase")
    op.drop_index("ix_jobs_workflow_id", table_name="jobs")
    op.drop_column("jobs", "workflow_id")
