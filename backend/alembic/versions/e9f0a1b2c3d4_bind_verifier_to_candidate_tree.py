"""Bind durable verification rows to a candidate tree hash, not a commit.

Revision ID: e9f0a1b2c3d4
Revises: d9e0f1a2b3c4
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "e9f0a1b2c3d4"
down_revision: Union[str, Sequence[str], None] = "d9e0f1a2b3c4"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Preserve all historical verification bindings while making the identity
    # type explicit. Existing values are commit hashes and remain valid hashes.
    op.alter_column(
        "verification_runs",
        "candidate_commit",
        new_column_name="candidate_hash",
        existing_type=sa.String(length=64),
        existing_nullable=False,
    )


def downgrade() -> None:
    op.alter_column(
        "verification_runs",
        "candidate_hash",
        new_column_name="candidate_commit",
        existing_type=sa.String(length=64),
        existing_nullable=False,
    )
