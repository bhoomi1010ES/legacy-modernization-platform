"""w06_artifact_lineage_and_provider_usage

Revision ID: a2b3c4d5e6f7
Revises: f8a9b0123c4d
Create Date: 2026-10-30 14:30:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "a2b3c4d5e6f7"
down_revision: Union[str, Sequence[str], None] = "f8a9b0123c4d"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Reconcile deployments where individual columns were added before the
    # migration revision was recorded. Only absent schema objects are created.
    bind = op.get_bind()

    def columns(table: str) -> set[str]:
        return {item["name"] for item in sa.inspect(bind).get_columns(table)}

    artifact_columns = columns("artifacts")
    for name, column in (
        ("schema_version", sa.Column("schema_version", sa.String(length=20), server_default="1.0.0", nullable=False)),
        ("is_invalidated", sa.Column("is_invalidated", sa.Boolean(), server_default=sa.text("false"), nullable=False)),
        ("invalidated_at", sa.Column("invalidated_at", sa.DateTime(timezone=True), nullable=True)),
        ("invalidation_reason", sa.Column("invalidation_reason", sa.String(length=512), nullable=True)),
        ("producer_run_id", sa.Column("producer_run_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("agent_runs.run_id", ondelete="SET NULL"), nullable=True)),
    ):
        if name not in artifact_columns:
            op.add_column("artifacts", column)
    if "ix_artifacts_producer_run_id" not in {i["name"] for i in sa.inspect(bind).get_indexes("artifacts")}:
        op.create_index("ix_artifacts_producer_run_id", "artifacts", ["producer_run_id"])

    if not sa.inspect(bind).has_table("artifact_dependencies"):
        op.create_table(
            "artifact_dependencies",
            sa.Column("dependency_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
            sa.Column("artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.artifact_id", ondelete="CASCADE"), nullable=False),
            sa.Column("ancestor_artifact_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("artifacts.artifact_id", ondelete="RESTRICT"), nullable=False),
            sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False),
            sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
            sa.UniqueConstraint("artifact_id", "ancestor_artifact_id", name="uq_artifact_dependency"),
        )
    for name, column in (
        ("ix_artifact_dependencies_job_id", "job_id"),
        ("ix_artifact_dependencies_artifact_id", "artifact_id"),
        ("ix_artifact_dependencies_ancestor_artifact_id", "ancestor_artifact_id"),
    ):
        if sa.inspect(bind).has_table("artifact_dependencies") and name not in {i["name"] for i in sa.inspect(bind).get_indexes("artifact_dependencies")}:
            op.create_index(name, "artifact_dependencies", [column])

    agent_columns = columns("agent_runs")
    for name, column in (
        ("reported_input_tokens", sa.Column("reported_input_tokens", sa.Integer(), nullable=True)),
        ("reported_output_tokens", sa.Column("reported_output_tokens", sa.Integer(), nullable=True)),
        ("provider_request_id", sa.Column("provider_request_id", sa.String(length=128), nullable=True)),
        ("provider_model_id", sa.Column("provider_model_id", sa.String(length=100), nullable=True)),
        ("pricing_table_version", sa.Column("pricing_table_version", sa.String(length=50), nullable=True)),
        ("estimated_cost", sa.Column("estimated_cost", sa.Numeric(10, 4), nullable=True)),
        ("billed_cost", sa.Column("billed_cost", sa.Numeric(10, 4), nullable=True)),
    ):
        if name not in agent_columns:
            op.add_column("agent_runs", column)


def downgrade() -> None:
    op.drop_column("agent_runs", "billed_cost")
    op.drop_column("agent_runs", "estimated_cost")
    op.drop_column("agent_runs", "pricing_table_version")
    op.drop_column("agent_runs", "provider_model_id")
    op.drop_column("agent_runs", "provider_request_id")
    op.drop_column("agent_runs", "reported_output_tokens")
    op.drop_column("agent_runs", "reported_input_tokens")

    op.drop_index("ix_artifact_dependencies_ancestor_artifact_id", table_name="artifact_dependencies")
    op.drop_index("ix_artifact_dependencies_artifact_id", table_name="artifact_dependencies")
    op.drop_index("ix_artifact_dependencies_job_id", table_name="artifact_dependencies")
    op.drop_table("artifact_dependencies")

    op.drop_index("ix_artifacts_producer_run_id", table_name="artifacts")
    op.drop_column("artifacts", "producer_run_id")
    op.drop_column("artifacts", "invalidation_reason")
    op.drop_column("artifacts", "invalidated_at")
    op.drop_column("artifacts", "is_invalidated")
    op.drop_column("artifacts", "schema_version")
