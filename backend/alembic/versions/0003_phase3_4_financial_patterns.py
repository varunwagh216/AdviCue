"""Add Phase 4 versioned cross-client pattern results.

Revision ID: 0003_phase34
Revises: 0002_phase2
"""
from alembic import op
import sqlalchemy as sa
revision='0003_phase34'
down_revision='0002_phase2'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('pattern_runs',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('actor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('rule_version',sa.String(20),nullable=False),
        sa.Column('as_of_date',sa.Date()),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('matched_count',sa.Integer(),nullable=False))
    op.create_index('ix_pattern_runs_organization_id','pattern_runs',['organization_id'])
    op.create_table('detected_patterns',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('run_id',sa.String(36),sa.ForeignKey('pattern_runs.id'),nullable=False),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('rule_id',sa.String(60),nullable=False),
        sa.Column('rule_version',sa.String(20),nullable=False),
        sa.Column('snapshot_date',sa.Date(),nullable=False),
        sa.Column('member_count',sa.Integer(),nullable=False),
        sa.Column('advisor_count',sa.Integer(),nullable=False),
        sa.Column('recorded_value_total',sa.Numeric(22,2),nullable=False),
        sa.Column('evidence_summary',sa.Text(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_detected_patterns_run_id','detected_patterns',['run_id'])
    op.create_index('ix_detected_patterns_organization_id','detected_patterns',['organization_id'])
    op.create_table('pattern_members',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('pattern_id',sa.String(36),sa.ForeignKey('detected_patterns.id'),nullable=False),
        sa.Column('investor_id',sa.String(40),sa.ForeignKey('investors.id'),nullable=False),
        sa.Column('advisor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('equity_pct',sa.Numeric(7,2),nullable=False),
        sa.Column('fixed_deposit_pct',sa.Numeric(7,2),nullable=False),
        sa.Column('recorded_value',sa.Numeric(22,2),nullable=False),
        sa.Column('evidence_source_row_ids',sa.JSON(),nullable=False),
        sa.UniqueConstraint('pattern_id','investor_id',name='uq_pattern_member'))
    op.create_index('ix_pattern_members_pattern_id','pattern_members',['pattern_id'])
    op.create_index('ix_pattern_members_investor_id','pattern_members',['investor_id'])

def downgrade():
    op.drop_index('ix_pattern_members_investor_id',table_name='pattern_members')
    op.drop_index('ix_pattern_members_pattern_id',table_name='pattern_members')
    op.drop_table('pattern_members')
    op.drop_index('ix_detected_patterns_organization_id',table_name='detected_patterns')
    op.drop_index('ix_detected_patterns_run_id',table_name='detected_patterns')
    op.drop_table('detected_patterns')
    op.drop_index('ix_pattern_runs_organization_id',table_name='pattern_runs')
    op.drop_table('pattern_runs')
