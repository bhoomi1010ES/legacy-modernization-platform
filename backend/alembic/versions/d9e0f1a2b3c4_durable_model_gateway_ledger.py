"""Persist chargeable model requests and global reserved/spent budget.

Revision ID: d9e0f1a2b3c4
Revises: b10c0de5f678
"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

from app.models.base import GUID

revision: str = "d9e0f1a2b3c4"
down_revision: Union[str, Sequence[str], None] = "b10c0de5f678"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "model_gateway_budgets",
        sa.Column("budget_id", sa.Integer(), primary_key=True),
        sa.Column("ceiling_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("reserved_usd", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column("spent_usd", sa.Numeric(12, 6), server_default="0", nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.CheckConstraint("budget_id = 1", name="ck_model_gateway_single_budget"),
        sa.CheckConstraint("reserved_usd >= 0 AND spent_usd >= 0", name="ck_model_gateway_nonnegative_budget"),
    )
    op.bulk_insert(
        sa.table(
            "model_gateway_budgets",
            sa.column("budget_id", sa.Integer()),
            sa.column("ceiling_usd", sa.Numeric(12, 6)),
            sa.column("reserved_usd", sa.Numeric(12, 6)),
            sa.column("spent_usd", sa.Numeric(12, 6)),
        ),
        [{"budget_id": 1, "ceiling_usd": 5, "reserved_usd": 0, "spent_usd": 0}],
    )
    op.create_table(
        "model_gateway_requests",
        sa.Column("request_id", sa.String(128), primary_key=True),
        sa.Column("job_id", GUID(), sa.ForeignKey("jobs.job_id", ondelete="SET NULL"), nullable=True),
        sa.Column("run_id", GUID(), sa.ForeignKey("agent_runs.run_id", ondelete="SET NULL"), nullable=True),
        sa.Column("provider", sa.String(50), nullable=False),
        sa.Column("requested_model", sa.String(100), nullable=False),
        sa.Column("actual_model", sa.String(100), nullable=True),
        sa.Column("prompt_revision", sa.String(100), nullable=False),
        sa.Column("status", sa.String(32), nullable=False),
        sa.Column("reserved_usd", sa.Numeric(12, 6), nullable=False),
        sa.Column("estimated_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("billed_cost_usd", sa.Numeric(12, 6), nullable=True),
        sa.Column("input_tokens", sa.Integer(), nullable=True),
        sa.Column("output_tokens", sa.Integer(), nullable=True),
        sa.Column("provider_request_id", sa.String(128), nullable=True),
        sa.Column("attempt_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("rate_limit_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("last_error_type", sa.String(100), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.create_index("ix_model_gateway_requests_job_id", "model_gateway_requests", ["job_id"])
    op.create_index("ix_model_gateway_requests_run_id", "model_gateway_requests", ["run_id"])
    op.create_index("ix_model_gateway_requests_status_created", "model_gateway_requests", ["status", "created_at"])


def downgrade() -> None:
    op.drop_index("ix_model_gateway_requests_status_created", table_name="model_gateway_requests")
    op.drop_index("ix_model_gateway_requests_run_id", table_name="model_gateway_requests")
    op.drop_index("ix_model_gateway_requests_job_id", table_name="model_gateway_requests")
    op.drop_table("model_gateway_requests")
    op.drop_table("model_gateway_budgets")
