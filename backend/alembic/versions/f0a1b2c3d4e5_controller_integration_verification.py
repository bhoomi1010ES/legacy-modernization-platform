"""Link independently controlled system verification without rewriting historical rows."""
from alembic import op
import sqlalchemy as sa
from app.models.base import GUID

revision = 'f0a1b2c3d4e5'
down_revision = 'e9f0a1b2c3d4'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('verification_runs') as batch:
        batch.alter_column('attempt_id',existing_type=GUID(),nullable=True)
        batch.add_column(sa.Column('integration_run_id',GUID(),nullable=True))
        batch.create_foreign_key('fk_verification_integration_run','agent_runs',['integration_run_id'],['run_id'],ondelete='CASCADE')
        batch.create_index('ix_verification_runs_integration_run_id',['integration_run_id'])


def downgrade():
    raise RuntimeError('Historical system verification evidence must be preserved; use a forward migration')
