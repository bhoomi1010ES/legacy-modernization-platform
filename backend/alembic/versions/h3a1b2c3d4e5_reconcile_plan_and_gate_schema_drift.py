"""Reconcile plan and gate schema drift.

Revision ID: h3a1b2c3d4e5
Revises: g2a1b2c3d4e5
Create Date: 2026-11-05 12:30:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "h3a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "g2a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop obsolete tasks table and its associated indexes
    op.execute(sa.text("DROP TABLE IF EXISTS tasks CASCADE;"))

    # 2. Drop obsolete columns from modules table
    op.execute(sa.text("ALTER TABLE modules DROP COLUMN IF EXISTS spec CASCADE;"))
    op.execute(sa.text("ALTER TABLE modules DROP COLUMN IF EXISTS locked_test_hash CASCADE;"))
    op.execute(sa.text("ALTER TABLE modules DROP COLUMN IF EXISTS locked_test_version CASCADE;"))

    # 3. Drop obsolete columns from gate_decisions table
    op.execute(sa.text("ALTER TABLE gate_decisions DROP COLUMN IF EXISTS artifact_hash CASCADE;"))
    op.execute(sa.text("ALTER TABLE gate_decisions DROP COLUMN IF EXISTS artifact_version CASCADE;"))
    op.execute(sa.text("ALTER TABLE gate_decisions DROP COLUMN IF EXISTS artifact_type CASCADE;"))
    op.execute(sa.text("ALTER TABLE gate_decisions DROP COLUMN IF EXISTS previous_decision_reference CASCADE;"))
    op.execute(sa.text("ALTER TABLE gate_decisions DROP COLUMN IF EXISTS approver_role CASCADE;"))


def downgrade() -> None:
    pass

