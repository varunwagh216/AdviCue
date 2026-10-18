"""Advice outcome snapshots, change-based monitoring and pilot observations."""
from alembic import op
import sqlalchemy as sa
revision='0013_connected_workspace'
down_revision='0012_evidence_pilot'
branch_labels=None
depends_on=None


def upgrade():
    for name,typ in [('already_known',sa.Boolean()),('discovery_note',sa.Text()),('missed_issue',sa.Boolean()),('voluntary_return',sa.Boolean())]:
        op.add_column('pilot_sessions',sa.Column(name,typ,nullable=True))
    op.add_column('pilot_sessions',sa.Column('sampling_method',sa.String(30),nullable=False,server_default='CLIENT_REVIEW'))
    op.create_table('monitoring_states',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('investor_id',sa.String(40),sa.ForeignKey('investors.id'),nullable=False),
        sa.Column('stream',sa.String(20),nullable=False),sa.Column('fingerprint',sa.String(64)),sa.Column('active',sa.Boolean(),nullable=False),
        sa.Column('current_case_id',sa.String(36),sa.ForeignKey('attention_cases.id')),sa.Column('checked_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('organization_id','investor_id','stream',name='uq_monitor_state'))
    op.create_table('advice_outcome_reviews',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('investor_id',sa.String(40),sa.ForeignKey('investors.id'),nullable=False),
        sa.Column('advisor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('advice_id',sa.String(36),sa.ForeignKey('advice_records.id'),nullable=False),
        sa.Column('evidence_id',sa.String(36),sa.ForeignKey('review_evidence.id')),sa.Column('result',sa.JSON(),nullable=False),
        sa.Column('note',sa.Text(),nullable=False),sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    for table in ('monitoring_states','advice_outcome_reviews'):
        for field in ('organization_id','investor_id'):
            op.create_index('ix_'+table+'_'+field,table,[field])
    op.create_index('ix_outcome_review_advice','advice_outcome_reviews',['advice_id'])


def downgrade():
    op.drop_table('advice_outcome_reviews');op.drop_table('monitoring_states')
    with op.batch_alter_table('pilot_sessions') as batch:
        for name in ('already_known','discovery_note','missed_issue','voluntary_return','sampling_method'):batch.drop_column(name)
