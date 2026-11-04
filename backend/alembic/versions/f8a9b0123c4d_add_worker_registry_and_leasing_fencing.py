"""add_worker_registry_and_leasing_fencing

Revision ID: f8a9b0123c4d
Revises: e7f8a9b0123c
Create Date: 2026-10-30 14:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = "f8a9b0123c4d"
down_revision: Union[str, Sequence[str], None] = "e7f8a9b0123c"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Create worker_registry table
    op.create_table(
        "worker_registry",
        sa.Column("worker_id", sa.String(length=100), primary_key=True, nullable=False),
        sa.Column("worker_type", sa.String(length=50), nullable=False),
        sa.Column("version", sa.String(length=50), nullable=False, server_default="1.0.0"),
        sa.Column("status", sa.String(length=30), nullable=False, server_default="ACTIVE"),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("last_heartbeat", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("metadata_payload", sa.JSON(), nullable=False, server_default="{}"),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    # 2. Add leasing and fencing columns to modules
    op.add_column("modules", sa.Column("lease_token", sa.String(length=64), nullable=True))
    op.add_column("modules", sa.Column("expected_input_hash", sa.String(length=128), nullable=True))
    op.add_column("modules", sa.Column("accepted_result_hash", sa.String(length=128), nullable=True))

    # 3. Add lease_token column to module_attempts
    op.add_column("module_attempts", sa.Column("lease_token", sa.String(length=64), nullable=True))


def downgrade() -> None:
    op.drop_column("module_attempts", "lease_token")
    op.drop_column("modules", "accepted_result_hash")
    op.drop_column("modules", "expected_input_hash")
    op.drop_column("modules", "lease_token")
    op.drop_table("worker_registry")

