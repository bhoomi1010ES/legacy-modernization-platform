"""w10 durable independent verification work items

Revision ID: a1b2c3d4e5f6
Revises: f8a9b0123c4d
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a1b2c3d4e5f6"
down_revision: Union[str, Sequence[str], None] = "f8a9b0123c4d"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.drop_constraint("chk_difference_classification", "test_results", type_="check")
    op.create_check_constraint(
        "chk_difference_classification", "test_results",
        "difference_classification IN ('NONE', 'REGRESSION', 'INTENDED_DIFFERENCE', 'NONDETERMINISTIC', 'TEST_DEFECT', 'UNOBSERVED')",
    )
    op.create_table(
        "verification_runs",
        sa.Column("verification_run_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("attempt_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("module_attempts.attempt_id", ondelete="CASCADE"), nullable=False),
        sa.Column("agent_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id", ondelete="SET NULL"), nullable=True),
        sa.Column("candidate_commit", sa.String(64), nullable=False),
        sa.Column("suite_hash", sa.String(128), nullable=False),
        sa.Column("profile_version", sa.String(50), nullable=False),
        sa.Column("profile_digest", sa.String(128), nullable=False),
        sa.Column("input_hash", sa.String(128), nullable=False),
        sa.Column("worker_id", sa.String(100), nullable=True),
        sa.Column("lease_token", sa.String(64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="QUEUED"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("evidence", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("evidence_hash", sa.String(128), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint("status IN ('QUEUED', 'RUNNING', 'PASS', 'FAIL', 'BLOCKED')", name="chk_verification_run_status"),
    )
    op.create_index("ix_verification_runs_attempt_id", "verification_runs", ["attempt_id"])
    op.create_index("ix_verification_runs_agent_run_id", "verification_runs", ["agent_run_id"])
    op.create_index("ix_verification_runs_worker_id", "verification_runs", ["worker_id"])


def downgrade() -> None:
    op.drop_index("ix_verification_runs_worker_id", table_name="verification_runs")
    op.drop_index("ix_verification_runs_agent_run_id", table_name="verification_runs")
    op.drop_index("ix_verification_runs_attempt_id", table_name="verification_runs")
    op.drop_table("verification_runs")
    op.drop_constraint("chk_difference_classification", "test_results", type_="check")
    op.create_check_constraint(
        "chk_difference_classification", "test_results",
        "difference_classification IN ('NONE', 'REGRESSION', 'INTENDED_DIFFERENCE', 'NONDETERMINISTIC', 'TEST_DEFECT')",
    )
