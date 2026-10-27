"""phase2 agent runtime persistence

Revision ID: a2c0f82d91b7
Revises: a10f845d3121
Create Date: 2026-10-22 12:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "a2c0f82d91b7"
down_revision: Union[str, Sequence[str], None] = "a10f845d3121"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("agent_runs", sa.Column("task_id", sa.String(100), nullable=True))
    op.add_column("agent_runs", sa.Column("correlation_id", sa.String(64), nullable=True))
    op.add_column("agent_runs", sa.Column("model_provider", sa.String(50), server_default="fake", nullable=False))
    op.add_column("agent_runs", sa.Column("failure_classification", sa.String(50), nullable=True))
    op.add_column("agent_runs", sa.Column("task_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False))
    op.add_column("agent_runs", sa.Column("trace_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False))
    op.add_column("agent_runs", sa.Column("output_payload", sa.JSON(), nullable=True))
    op.add_column("agent_runs", sa.Column("input_artifact_refs", sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
    op.add_column("agent_runs", sa.Column("output_artifact_refs", sa.JSON(), server_default=sa.text("'[]'"), nullable=False))
    op.add_column("agent_runs", sa.Column("cancel_requested", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.create_index("ix_agent_runs_task_id", "agent_runs", ["task_id"])
    op.create_index("ix_agent_runs_correlation_id", "agent_runs", ["correlation_id"])


def downgrade() -> None:
    op.drop_index("ix_agent_runs_correlation_id", table_name="agent_runs")
    op.drop_index("ix_agent_runs_task_id", table_name="agent_runs")
    for column in (
        "cancel_requested", "output_artifact_refs", "input_artifact_refs", "output_payload",
        "trace_payload", "task_payload", "failure_classification", "model_provider", "correlation_id", "task_id",
    ):
        op.drop_column("agent_runs", column)
