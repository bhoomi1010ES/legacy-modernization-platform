"""Remove RBAC and roles, retaining normal authentication.

Revision ID: i4a1b2c3d4e5
Revises: h3a1b2c3d4e5
Create Date: 2026-11-06 15:15:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "i4a1b2c3d4e5"
down_revision: Union[str, Sequence[str], None] = "h3a1b2c3d4e5"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. Drop foreign key constraint from job_memberships to roles
    op.execute(sa.text("ALTER TABLE job_memberships DROP CONSTRAINT IF EXISTS job_memberships_role_id_fkey CASCADE;"))

    # 2. Drop index on user_id and role_id if exists
    op.execute(sa.text("DROP INDEX IF EXISTS ix_job_membership_user_role;"))

    # 3. Drop role_id column from job_memberships
    op.execute(sa.text("ALTER TABLE job_memberships DROP COLUMN IF EXISTS role_id CASCADE;"))

    # 4. Drop obsolete roles table
    op.execute(sa.text("DROP TABLE IF EXISTS roles CASCADE;"))


def downgrade() -> None:
    pass

