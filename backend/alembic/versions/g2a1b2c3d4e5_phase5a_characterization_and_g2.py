"""Create Phase 5A Characterization and Gate G2 tables.

Revision ID: g2a1b2c3d4e5
Revises: f1b2c3d4e5f6
Create Date: 2026-11-04 15:15:00.000000
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
from app.models.base import GUID

# revision identifiers, used by Alembic.
revision = 'g2a1b2c3d4e5'
down_revision = 'f1b2c3d4e5f6'
branch_labels = None
depends_on = None


def upgrade() -> None:
    # 1. characterization_executions
    op.create_table(
        'characterization_executions',
        sa.Column('execution_id', sa.String(length=64), nullable=False),
        sa.Column('job_id', GUID(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='PENDING'),
        sa.Column('stage', sa.String(length=64), nullable=False, server_default='INITIALIZING'),
        sa.Column('stage_progress_pct', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_scenarios_executed', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('total_workflows_characterized', sa.Integer(), nullable=False, server_default='0'),
        sa.Column('summary', sa.Text(), nullable=True),
        sa.Column('error_message', sa.Text(), nullable=True),
        sa.Column('duration_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('started_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('completed_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.job_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('execution_id'),
    )
    op.create_index('ix_characterization_executions_job_id', 'characterization_executions', ['job_id'])
    op.create_index('ix_characterization_executions_status', 'characterization_executions', ['status'])

    # 2. characterization_suites
    op.create_table(
        'characterization_suites',
        sa.Column('suite_id', sa.String(length=64), nullable=False),
        sa.Column('job_id', GUID(), nullable=False),
        sa.Column('execution_id', sa.String(length=64), nullable=False),
        sa.Column('version', sa.Integer(), nullable=False, server_default='1'),
        sa.Column('content_hash', sa.String(length=64), nullable=False),
        sa.Column('suite_data', sa.JSON(), nullable=False),
        sa.Column('is_partial', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('is_frozen', sa.Boolean(), nullable=False, server_default=sa.text('false')),
        sa.Column('frozen_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['execution_id'], ['characterization_executions.execution_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.job_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('suite_id'),
        sa.UniqueConstraint('job_id', 'version', name='uq_char_suite_job_version'),
    )
    op.create_index('ix_characterization_suites_job_id', 'characterization_suites', ['job_id'])
    op.create_index('ix_characterization_suites_is_frozen', 'characterization_suites', ['is_frozen'])

    # 3. characterization_scenarios
    op.create_table(
        'characterization_scenarios',
        sa.Column('scenario_id', sa.String(length=64), nullable=False),
        sa.Column('execution_id', sa.String(length=64), nullable=False),
        sa.Column('workflow_id', sa.String(length=128), nullable=False),
        sa.Column('scenario_type', sa.String(length=64), nullable=False),
        sa.Column('objective', sa.Text(), nullable=False),
        sa.Column('status', sa.String(length=32), nullable=False, server_default='PROPOSED'),
        sa.Column('exit_code', sa.Integer(), nullable=True),
        sa.Column('passed', sa.Boolean(), nullable=True),
        sa.Column('duration_ms', sa.Float(), nullable=False, server_default='0.0'),
        sa.Column('scenario_data', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['execution_id'], ['characterization_executions.execution_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('scenario_id'),
    )
    op.create_index('ix_characterization_scenarios_execution_id', 'characterization_scenarios', ['execution_id'])
    op.create_index('ix_characterization_scenarios_workflow_id', 'characterization_scenarios', ['workflow_id'])

    # 4. characterization_events
    op.create_table(
        'characterization_events',
        sa.Column('event_id', sa.String(length=64), nullable=False),
        sa.Column('execution_id', sa.String(length=64), nullable=False),
        sa.Column('sequence_number', sa.Integer(), nullable=False),
        sa.Column('stage', sa.String(length=64), nullable=False),
        sa.Column('event_type', sa.String(length=64), nullable=False),
        sa.Column('message', sa.Text(), nullable=False),
        sa.Column('payload', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['execution_id'], ['characterization_executions.execution_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('event_id'),
    )
    op.create_index('ix_characterization_events_execution_id', 'characterization_events', ['execution_id'])
    op.create_index('ix_char_events_exec_seq', 'characterization_events', ['execution_id', 'sequence_number'])

    # 5. gate_g2_approvals
    op.create_table(
        'gate_g2_approvals',
        sa.Column('approval_id', sa.String(length=64), nullable=False),
        sa.Column('job_id', GUID(), nullable=False),
        sa.Column('suite_id', sa.String(length=64), nullable=False),
        sa.Column('suite_version', sa.Integer(), nullable=False),
        sa.Column('suite_content_hash', sa.String(length=64), nullable=False),
        sa.Column('decision', sa.String(length=32), nullable=False),
        sa.Column('decided_by', sa.String(length=128), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('conditions', sa.JSON(), nullable=True),
        sa.Column('is_valid', sa.Boolean(), nullable=False, server_default=sa.text('true')),
        sa.Column('invalidation_reason', sa.Text(), nullable=True),
        sa.Column('decided_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.ForeignKeyConstraint(['job_id'], ['jobs.job_id'], ondelete='CASCADE'),
        sa.ForeignKeyConstraint(['suite_id'], ['characterization_suites.suite_id'], ondelete='CASCADE'),
        sa.PrimaryKeyConstraint('approval_id'),
    )
    op.create_index('ix_gate_g2_approvals_job_id', 'gate_g2_approvals', ['job_id'])
    op.create_index('ix_gate_g2_approvals_suite_id', 'gate_g2_approvals', ['suite_id'])


def downgrade() -> None:
    op.drop_table('gate_g2_approvals')
    op.drop_table('characterization_events')
    op.drop_table('characterization_scenarios')
    op.drop_table('characterization_suites')
    op.drop_table('characterization_executions')

