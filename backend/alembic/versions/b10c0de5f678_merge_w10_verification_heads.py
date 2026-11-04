"""merge W08 module-plan and W10 verification migration heads

Revision ID: b10c0de5f678
Revises: a1b2c3d4e5f6, c5d6e7f8091a
"""
from typing import Sequence, Union

revision: str = "b10c0de5f678"
down_revision: Union[str, Sequence[str], None] = ("a1b2c3d4e5f6", "c5d6e7f8091a")
branch_labels = None
depends_on = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
