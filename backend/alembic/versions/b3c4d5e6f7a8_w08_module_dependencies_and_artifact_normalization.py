"""w08_module_dependencies_and_artifact_normalization

Revision ID: b3c4d5e6f7a8
Revises: a2b3c4d5e6f7
Create Date: 2026-10-30 16:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "b3c4d5e6f7a8"
down_revision: Union[str, Sequence[str], None] = "a2b3c4d5e6f7"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create module_dependencies normalized table
    op.create_table(
        "module_dependencies",
        sa.Column("dependency_id", postgresql.UUID(as_uuid=True), primary_key=True, nullable=False),
        sa.Column("job_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("jobs.job_id", ondelete="CASCADE"), nullable=False),
        sa.Column("parent_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("modules.module_id", ondelete="CASCADE"), nullable=False),
        sa.Column("child_id", postgresql.UUID(as_uuid=True), sa.ForeignKey("modules.module_id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.func.now(), nullable=False),
        sa.UniqueConstraint("parent_id", "child_id", name="uq_module_dependency_parent_child"),
    )
    op.create_index("ix_module_dependencies_job_id", "module_dependencies", ["job_id"])
    op.create_index("ix_module_dependencies_parent_id", "module_dependencies", ["parent_id"])
    op.create_index("ix_module_dependencies_child_id", "module_dependencies", ["child_id"])

    # 2. Add rich contract, testing, and resource columns to modules
    op.add_column("modules", sa.Column("interfaces", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("modules", sa.Column("allowed_output_paths", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("modules", sa.Column("required_tests", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("modules", sa.Column("schema_dependencies", sa.JSON(), server_default="[]", nullable=False))
    op.add_column("modules", sa.Column("expected_resources", sa.JSON(), server_default="{}", nullable=False))

    # 3. Data migration: safely deduplicate and normalize legacy artifact types to canonical uppercase snake_case
    normalizations = [
        ("ConversionPlan", "CONVERSION_PLAN"),
        ("TargetBlueprint", "TARGET_BLUEPRINT"),
        ("Blueprint", "TARGET_BLUEPRINT"),
        ("FeasibilityReport", "FEASIBILITY_REPORT"),
        ("CharacterizationSuite", "CHARACTERIZATION_SUITE"),
        ("SchemaMigrationPlan", "SCHEMA_MIGRATION_PLAN"),
        ("SchemaPlan", "SCHEMA_MIGRATION_PLAN"),
        ("RepositorySnapshot", "REPOSITORY_SNAPSHOT"),
        ("RepositoryInventory", "REPOSITORY_INVENTORY"),
        ("LegacyModel", "LEGACY_MODEL"),
    ]

    for legacy_type, canonical_type in normalizations:
        # Delete duplicate rows that would violate uq_artifact_version
        op.execute(f"""
            DELETE FROM artifacts a1
            WHERE a1.artifact_type = '{legacy_type}'
              AND EXISTS (
                SELECT 1 FROM artifacts a2
                WHERE a2.job_id = a1.job_id
                  AND a2.artifact_type = '{canonical_type}'
                  AND a2.version = a1.version
              )
        """)
        # Update remaining legacy rows to canonical
        op.execute(f"""
            UPDATE artifacts
            SET artifact_type = '{canonical_type}'
            WHERE artifact_type = '{legacy_type}'
        """)


def downgrade() -> None:
    op.drop_column("modules", "expected_resources")
    op.drop_column("modules", "schema_dependencies")
    op.drop_column("modules", "required_tests")
    op.drop_column("modules", "allowed_output_paths")
    op.drop_column("modules", "interfaces")
    op.drop_index("ix_module_dependencies_child_id", table_name="module_dependencies")
    op.drop_index("ix_module_dependencies_parent_id", table_name="module_dependencies")
    op.drop_index("ix_module_dependencies_job_id", table_name="module_dependencies")
    op.drop_table("module_dependencies")
