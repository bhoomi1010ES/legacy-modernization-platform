"""Append explicit request attempt/selection and reconciliation evidence.

Historical rows stay null where the earlier implementation recorded no evidence.
"""
from alembic import op
import sqlalchemy as sa
from app.models.base import GUID

revision='f1b2c3d4e5f6'
down_revision='f0a1b2c3d4e5'
branch_labels=None
depends_on=None


def upgrade():
    with op.batch_alter_table('model_gateway_requests') as batch:
        batch.add_column(sa.Column('attempt_id',GUID(),nullable=True))
        batch.add_column(sa.Column('selection_hash',sa.String(64),nullable=True))
        batch.add_column(sa.Column('reconciliation_status',sa.String(40),nullable=True))
        batch.add_column(sa.Column('charged_cost_usd',sa.Numeric(12,6),nullable=True))
        batch.add_column(sa.Column('released_usd',sa.Numeric(12,6),nullable=True))
        batch.create_foreign_key('fk_gateway_request_attempt','module_attempts',['attempt_id'],['attempt_id'],ondelete='SET NULL')
        batch.create_index('ix_model_gateway_requests_attempt_id',['attempt_id'])


def downgrade():
    raise RuntimeError('Request accounting evidence must be preserved; use a forward migration')
