"""phase3 durable supervisor workflow

Revision ID: b3d4e5f60718
Revises: a2c0f82d91b7
Create Date: 2026-10-22 15:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.models.base import GUID

revision: str = "b3d4e5f60718"
down_revision: Union[str, Sequence[str], None] = "a2c0f82d91b7"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for column in (
        sa.Column("workflow_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("active_node", sa.String(100), server_default="created", nullable=False),
        sa.Column("paused_from_status", sa.String(50), nullable=True),
        sa.Column("blocking_reason", sa.Text(), nullable=True),
        sa.Column("workflow_retry_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("max_parallel_tasks", sa.Integer(), server_default="3", nullable=False),
        sa.Column("provider_concurrency_limit", sa.Integer(), server_default="3", nullable=False),
        sa.Column("sandbox_concurrency_limit", sa.Integer(), server_default="3", nullable=False),
        sa.Column("last_checkpoint_sequence", sa.Integer(), server_default="0", nullable=False),
    ):
        op.add_column("jobs", column)

    for column in (
        sa.Column("dependency_module_ids", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("budget_limit_usd", sa.Numeric(10, 4), server_default="0", nullable=False),
        sa.Column("budget_used_usd", sa.Numeric(10, 4), server_default="0", nullable=False),
        sa.Column("lease_owner", sa.String(255), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("retry_count", sa.Integer(), server_default="0", nullable=False),
    ):
        op.add_column("modules", column)

    op.add_column("test_results", sa.Column("invalidated", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("test_results", sa.Column("invalidation_reason", sa.Text(), nullable=True))

    op.create_table(
        "workflow_checkpoints",
        sa.Column("checkpoint_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("sequence", sa.Integer(), nullable=False),
        sa.Column("checkpoint_kind", sa.String(20), nullable=False),
        sa.Column("node_name", sa.String(100), nullable=False),
        sa.Column("state_payload", sa.JSON(), nullable=False),
        sa.Column("correlation_id", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("checkpoint_kind IN ('BEFORE', 'AFTER', 'INTERRUPT', 'RECOVERY')", name="chk_workflow_checkpoint_kind"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("checkpoint_id"),
        sa.UniqueConstraint("job_id", "sequence", name="uq_workflow_checkpoint_job_sequence"),
    )
    op.create_index("ix_workflow_checkpoints_job_id", "workflow_checkpoints", ["job_id"])
    op.create_index("ix_workflow_checkpoints_correlation_id", "workflow_checkpoints", ["correlation_id"])
    op.create_index("ix_workflow_checkpoint_job_created", "workflow_checkpoints", ["job_id", "created_at"])

    op.create_table(
        "workflow_gates",
        sa.Column("gate_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("gate_type", sa.String(10), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(30), server_default="PENDING", nullable=False),
        sa.Column("artifact_ids", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("artifact_hashes", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("blocking_reason", sa.Text(), nullable=True),
        sa.Column("supersedes_gate_id", GUID(), nullable=True),
        sa.Column("requested_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("decided_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint("gate_type IN ('G1', 'G2', 'G3', 'G4')", name="chk_workflow_gate_type"),
        sa.CheckConstraint("status IN ('PENDING', 'APPROVED', 'REJECTED', 'NEEDS_CHANGES', 'INVALIDATED', 'TIMED_OUT')", name="chk_workflow_gate_status"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["supersedes_gate_id"], ["workflow_gates.gate_id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("gate_id"),
        sa.UniqueConstraint("job_id", "gate_type", "version", name="uq_workflow_gate_job_type_version"),
    )
    op.create_index("ix_workflow_gates_job_id", "workflow_gates", ["job_id"])
    op.create_index("ix_workflow_gate_job_status", "workflow_gates", ["job_id", "status"])

    op.create_table(
        "workflow_outbox",
        sa.Column("outbox_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("idempotency_key", sa.String(255), nullable=False),
        sa.Column("event_type", sa.String(100), nullable=False),
        sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("status", sa.String(30), server_default="PENDING", nullable=False),
        sa.Column("attempts", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("available_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("processed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint("status IN ('PENDING', 'PROCESSING', 'PROCESSED', 'DEAD_LETTER')", name="chk_workflow_outbox_status"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("outbox_id"),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_workflow_outbox_job_id", "workflow_outbox", ["job_id"])
    op.create_index("ix_workflow_outbox_ready", "workflow_outbox", ["status", "available_at"])

    op.add_column("gate_decisions", sa.Column("gate_id", GUID(), nullable=True))
    op.add_column("gate_decisions", sa.Column("selected_options", sa.JSON(), server_default=sa.text("'{}'"), nullable=False))
    op.add_column("gate_decisions", sa.Column("artifact_hashes", sa.JSON(), server_default=sa.text("'{}'"), nullable=False))
    op.add_column("gate_decisions", sa.Column("idempotency_key", sa.String(255), nullable=True))
    op.create_foreign_key("fk_gate_decisions_workflow_gate", "gate_decisions", "workflow_gates", ["gate_id"], ["gate_id"], ondelete="SET NULL")
    op.create_index("ix_gate_decisions_gate_id", "gate_decisions", ["gate_id"])
    op.create_unique_constraint("uq_gate_decisions_idempotency_key", "gate_decisions", ["idempotency_key"])
    op.drop_constraint("chk_gate_decision", "gate_decisions", type_="check")
    op.execute("UPDATE gate_decisions SET decision = 'NEEDS_CHANGES' WHERE decision = 'REQUEST_CHANGES'")
    op.create_check_constraint("chk_gate_decision", "gate_decisions", "decision IN ('APPROVED', 'REJECTED', 'NEEDS_CHANGES')")


def downgrade() -> None:
    op.drop_constraint("chk_gate_decision", "gate_decisions", type_="check")
    op.execute("UPDATE gate_decisions SET decision = 'REQUEST_CHANGES' WHERE decision = 'NEEDS_CHANGES'")
    op.create_check_constraint("chk_gate_decision", "gate_decisions", "decision IN ('APPROVED', 'REJECTED', 'REQUEST_CHANGES')")
    op.drop_constraint("uq_gate_decisions_idempotency_key", "gate_decisions", type_="unique")
    op.drop_index("ix_gate_decisions_gate_id", table_name="gate_decisions")
    op.drop_constraint("fk_gate_decisions_workflow_gate", "gate_decisions", type_="foreignkey")
    for column in ("idempotency_key", "artifact_hashes", "selected_options", "gate_id"):
        op.drop_column("gate_decisions", column)
    op.drop_table("workflow_outbox")
    op.drop_table("workflow_gates")
    op.drop_table("workflow_checkpoints")
    for column in ("invalidation_reason", "invalidated"):
        op.drop_column("test_results", column)
    for column in ("retry_count", "lease_expires_at", "lease_owner", "budget_used_usd", "budget_limit_usd", "dependency_module_ids"):
        op.drop_column("modules", column)
    for column in (
        "last_checkpoint_sequence", "sandbox_concurrency_limit", "provider_concurrency_limit",
        "max_parallel_tasks", "workflow_retry_count", "blocking_reason", "paused_from_status",
        "active_node", "workflow_version",
    ):
        op.drop_column("jobs", column)
