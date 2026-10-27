"""phase4 intake, legacy analyzer, architect, feasibility, and planner persistence

Revision ID: c4d5e6f70819
Revises: b3d4e5f60718
Create Date: 2026-10-22 17:00:00.000000
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.models.base import GUID

revision: str = "c4d5e6f70819"
down_revision: Union[str, Sequence[str], None] = "b3d4e5f60718"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "repository_snapshots",
        sa.Column("snapshot_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("source_type", sa.String(50), server_default="git", nullable=False),
        sa.Column("source_ref", sa.String(512), nullable=False),
        sa.Column("commit_sha", sa.String(128), nullable=True),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("inventory_hash", sa.String(128), nullable=False),
        sa.Column("file_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("archive_size_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("tech_profile", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("metadata_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("snapshot_id"),
        sa.UniqueConstraint("job_id", "version", name="uq_repo_snapshot_job_version"),
    )
    op.create_index("ix_repository_snapshots_job_id", "repository_snapshots", ["job_id"])
    op.create_index("ix_repository_snapshots_content_hash", "repository_snapshots", ["content_hash"])
    op.create_index("ix_repo_snapshots_job_created", "repository_snapshots", ["job_id", "created_at"])

    op.create_table(
        "repository_inventories",
        sa.Column("inventory_id", GUID(), nullable=False),
        sa.Column("snapshot_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("total_files", sa.Integer(), server_default="0", nullable=False),
        sa.Column("total_bytes", sa.Integer(), server_default="0", nullable=False),
        sa.Column("files_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("directories_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("inventory_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["snapshot_id"], ["repository_snapshots.snapshot_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("inventory_id"),
    )
    op.create_index("ix_repository_inventories_snapshot_id", "repository_inventories", ["snapshot_id"])
    op.create_index("ix_repository_inventories_job_id", "repository_inventories", ["job_id"])
    op.create_index("ix_repository_inventories_hash", "repository_inventories", ["inventory_hash"])

    op.create_table(
        "analysis_runs",
        sa.Column("run_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("snapshot_id", GUID(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(50), server_default="RUNNING", nullable=False),
        sa.Column("coordinator_notes", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["repository_snapshots.snapshot_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("job_id", "version", name="uq_analysis_run_job_version"),
    )
    op.create_index("ix_analysis_runs_job_id", "analysis_runs", ["job_id"])

    op.create_table(
        "analysis_workers",
        sa.Column("worker_id", GUID(), nullable=False),
        sa.Column("run_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("analysis_type", sa.String(100), nullable=False),
        sa.Column("status", sa.String(50), server_default="PENDING", nullable=False),
        sa.Column("input_scope", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("findings", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("confidence", sa.String(50), server_default="CONFIRMED", nullable=False),
        sa.Column("warnings", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("errors", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("model_version", sa.String(100), server_default="deterministic-scanner", nullable=False),
        sa.Column("prompt_version", sa.String(50), server_default="v4.0", nullable=False),
        sa.Column("artifact_hash", sa.String(128), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["run_id"], ["analysis_runs.run_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("worker_id"),
    )
    op.create_index("ix_analysis_workers_run_id", "analysis_workers", ["run_id"])
    op.create_index("ix_analysis_workers_job_id", "analysis_workers", ["job_id"])

    op.create_table(
        "legacy_models",
        sa.Column("model_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("snapshot_id", GUID(), nullable=False),
        sa.Column("modules_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("dependencies_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("interfaces_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("persistence_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("configurations_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("tests_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("risks_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("conflicts_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["snapshot_id"], ["repository_snapshots.snapshot_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("model_id"),
        sa.UniqueConstraint("job_id", "version", name="uq_legacy_model_job_version"),
    )
    op.create_index("ix_legacy_models_job_id", "legacy_models", ["job_id"])
    op.create_index("ix_legacy_models_content_hash", "legacy_models", ["content_hash"])

    op.create_table(
        "analysis_evidence",
        sa.Column("evidence_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("source_artifact", sa.String(128), nullable=False),
        sa.Column("source_path", sa.String(512), nullable=False),
        sa.Column("source_location", sa.String(255), nullable=True),
        sa.Column("evidence_type", sa.String(100), nullable=False),
        sa.Column("evidence_excerpt", sa.Text(), nullable=True),
        sa.Column("content_hash", sa.String(128), nullable=True),
        sa.Column("confidence", sa.String(50), server_default="CONFIRMED", nullable=False),
        sa.Column("agent_name", sa.String(100), server_default="analyzer", nullable=False),
        sa.Column("artifact_version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("evidence_id"),
    )
    op.create_index("ix_analysis_evidence_job_id", "analysis_evidence", ["job_id"])
    op.create_index("ix_analysis_evidence_job_path", "analysis_evidence", ["job_id", "source_path"])

    op.create_table(
        "analysis_conflicts",
        sa.Column("conflict_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("subject", sa.String(255), nullable=False),
        sa.Column("claim_a", sa.Text(), nullable=False),
        sa.Column("claim_b", sa.Text(), nullable=False),
        sa.Column("evidence_a", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("evidence_b", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("confidence_a", sa.String(50), server_default="CONFIRMED", nullable=False),
        sa.Column("confidence_b", sa.String(50), server_default="CONFIRMED", nullable=False),
        sa.Column("resolution_status", sa.String(50), server_default="UNRESOLVED", nullable=False),
        sa.Column("resolution_notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("conflict_id"),
    )
    op.create_index("ix_analysis_conflicts_job_id", "analysis_conflicts", ["job_id"])

    op.create_table(
        "target_blueprints",
        sa.Column("blueprint_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(50), server_default="DRAFT", nullable=False),
        sa.Column("target_stack", sa.String(255), nullable=False),
        sa.Column("target_architecture", sa.String(255), nullable=False),
        sa.Column("components_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("interfaces_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("data_model_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("integration_contracts_payload", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("constraints_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("accepted_decisions", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("evidence_refs", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("created_by", sa.String(100), server_default="architect-agent", nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("blueprint_id"),
        sa.UniqueConstraint("job_id", "version", name="uq_target_blueprint_job_version"),
    )
    op.create_index("ix_target_blueprints_job_id", "target_blueprints", ["job_id"])
    op.create_index("ix_target_blueprints_content_hash", "target_blueprints", ["content_hash"])

    op.create_table(
        "feasibility_reports",
        sa.Column("report_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("blueprint_version", sa.Integer(), nullable=False),
        sa.Column("legacy_model_version", sa.Integer(), nullable=False),
        sa.Column("overall_score", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("unsupported_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("custom_build_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("substitute_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("unknown_count", sa.Integer(), server_default="0", nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("report_id"),
        sa.UniqueConstraint("job_id", "version", name="uq_feasibility_report_job_version"),
    )
    op.create_index("ix_feasibility_reports_job_id", "feasibility_reports", ["job_id"])

    op.create_table(
        "feasibility_capabilities",
        sa.Column("capability_record_id", GUID(), nullable=False),
        sa.Column("report_id", GUID(), nullable=False),
        sa.Column("capability_id", sa.String(100), nullable=False),
        sa.Column("category", sa.String(50), nullable=False),
        sa.Column("legacy_requirement", sa.Text(), nullable=False),
        sa.Column("target_requirement", sa.Text(), nullable=False),
        sa.Column("classification", sa.String(50), nullable=False),
        sa.Column("confidence", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("tool_dependency", sa.String(100), nullable=True),
        sa.Column("effort", sa.String(20), server_default="MEDIUM", nullable=False),
        sa.Column("risk", sa.String(20), server_default="MEDIUM", nullable=False),
        sa.Column("verification_impact", sa.Text(), nullable=False),
        sa.Column("recommendation", sa.Text(), nullable=False),
        sa.Column("evidence", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.ForeignKeyConstraint(["report_id"], ["feasibility_reports.report_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("capability_record_id"),
    )
    op.create_index("ix_feasibility_capabilities_report_id", "feasibility_capabilities", ["report_id"])

    op.create_table(
        "feasibility_decisions",
        sa.Column("decision_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("capability_id", sa.String(100), nullable=True),
        sa.Column("decision", sa.String(50), nullable=False),
        sa.Column("reason", sa.Text(), nullable=False),
        sa.Column("actor", sa.String(100), nullable=False),
        sa.Column("previous_feasibility_version", sa.Integer(), nullable=False),
        sa.Column("resulting_blueprint_version", sa.Integer(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("decision_id"),
    )
    op.create_index("ix_feasibility_decisions_job_id", "feasibility_decisions", ["job_id"])

    op.create_table(
        "planner_runs",
        sa.Column("run_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("blueprint_version", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("status", sa.String(50), server_default="RUNNING", nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("run_id"),
        sa.UniqueConstraint("job_id", "version", name="uq_planner_run_job_version"),
    )
    op.create_index("ix_planner_runs_job_id", "planner_runs", ["job_id"])

    op.create_table(
        "planner_outputs",
        sa.Column("output_id", GUID(), nullable=False),
        sa.Column("run_id", GUID(), nullable=False),
        sa.Column("module_id", sa.String(100), nullable=False),
        sa.Column("unit_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["planner_runs.run_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("output_id"),
    )
    op.create_index("ix_planner_outputs_run_id", "planner_outputs", ["run_id"])

    op.create_table(
        "conversion_plans",
        sa.Column("plan_id", GUID(), nullable=False),
        sa.Column("job_id", GUID(), nullable=False),
        sa.Column("version", sa.Integer(), server_default="1", nullable=False),
        sa.Column("blueprint_version", sa.Integer(), nullable=False),
        sa.Column("validation_status", sa.String(50), server_default="VALID", nullable=False),
        sa.Column("is_valid_dag", sa.Boolean(), server_default=sa.true(), nullable=False),
        sa.Column("total_estimate_hours", sa.Float(), server_default="0.0", nullable=False),
        sa.Column("risk_summary_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("validation_payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.Column("content_hash", sa.String(128), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["job_id"], ["jobs.job_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("plan_id"),
        sa.UniqueConstraint("job_id", "version", name="uq_conversion_plan_job_version"),
    )
    op.create_index("ix_conversion_plans_job_id", "conversion_plans", ["job_id"])
    op.create_index("ix_conversion_plans_content_hash", "conversion_plans", ["content_hash"])

    op.create_table(
        "conversion_plan_modules",
        sa.Column("module_record_id", GUID(), nullable=False),
        sa.Column("plan_id", GUID(), nullable=False),
        sa.Column("module_id", sa.String(100), nullable=False),
        sa.Column("responsibility", sa.Text(), nullable=False),
        sa.Column("wave_number", sa.Integer(), server_default="1", nullable=False),
        sa.Column("estimate_hours", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("risk", sa.String(20), server_default="MEDIUM", nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["conversion_plans.plan_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("module_record_id"),
    )
    op.create_index("ix_conversion_plan_modules_plan_id", "conversion_plan_modules", ["plan_id"])

    op.create_table(
        "conversion_plan_tasks",
        sa.Column("task_record_id", GUID(), nullable=False),
        sa.Column("plan_id", GUID(), nullable=False),
        sa.Column("task_id", sa.String(100), nullable=False),
        sa.Column("module_id", sa.String(100), nullable=False),
        sa.Column("title", sa.String(255), nullable=False),
        sa.Column("estimate_hours", sa.Float(), server_default="1.0", nullable=False),
        sa.Column("risk", sa.String(20), server_default="MEDIUM", nullable=False),
        sa.Column("acceptance_criteria", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("dependencies", sa.JSON(), server_default=sa.text("'[]'"), nullable=False),
        sa.Column("payload", sa.JSON(), server_default=sa.text("'{}'"), nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["conversion_plans.plan_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("task_record_id"),
    )
    op.create_index("ix_conversion_plan_tasks_plan_id", "conversion_plan_tasks", ["plan_id"])

    op.create_table(
        "conversion_plan_dependencies",
        sa.Column("dependency_id", GUID(), nullable=False),
        sa.Column("plan_id", GUID(), nullable=False),
        sa.Column("source", sa.String(100), nullable=False),
        sa.Column("target", sa.String(100), nullable=False),
        sa.Column("dependency_type", sa.String(50), server_default="CODE_IMPORT", nullable=False),
        sa.Column("confidence", sa.String(50), server_default="CONFIRMED", nullable=False),
        sa.ForeignKeyConstraint(["plan_id"], ["conversion_plans.plan_id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("dependency_id"),
    )
    op.create_index("ix_conversion_plan_dependencies_plan_id", "conversion_plan_dependencies", ["plan_id"])


def downgrade() -> None:
    op.drop_table("conversion_plan_dependencies")
    op.drop_table("conversion_plan_tasks")
    op.drop_table("conversion_plan_modules")
    op.drop_table("conversion_plans")
    op.drop_table("planner_outputs")
    op.drop_table("planner_runs")
    op.drop_table("feasibility_decisions")
    op.drop_table("feasibility_capabilities")
    op.drop_table("feasibility_reports")
    op.drop_table("target_blueprints")
    op.drop_table("analysis_conflicts")
    op.drop_table("analysis_evidence")
    op.drop_table("legacy_models")
    op.drop_table("analysis_workers")
    op.drop_table("analysis_runs")
    op.drop_table("repository_inventories")
    op.drop_table("repository_snapshots")
