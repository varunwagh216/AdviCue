"""Phase 5 Attention Radar and Phase 6 Advice Ledger and tasks.

Revision ID: 0004_phase56
Revises: 0003_phase34
"""
from alembic import op
import sqlalchemy as sa

revision = '0004_phase56'
down_revision = '0003_phase34'
branch_labels = None
depends_on = None


def upgrade():
    op.create_table('attention_cases',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('investor_id', sa.String(40), sa.ForeignKey('investors.id'), nullable=False),
        sa.Column('advisor_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('pattern_id', sa.String(36), sa.ForeignKey('detected_patterns.id'), nullable=False),
        sa.Column('rule_id', sa.String(60), nullable=False),
        sa.Column('rule_version', sa.String(20), nullable=False),
        sa.Column('source_date', sa.Date(), nullable=False),
        sa.Column('priority', sa.String(10), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('title', sa.String(180), nullable=False),
        sa.Column('reason', sa.Text(), nullable=False),
        sa.Column('suggested_action', sa.Text(), nullable=False),
        sa.Column('evidence_source_row_ids', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('resolved_at', sa.DateTime(timezone=True)),
        sa.Column('resolution_note', sa.Text()),
        sa.Column('resolved_by', sa.String(36), sa.ForeignKey('users.id')),
        sa.UniqueConstraint('organization_id', 'investor_id', 'rule_id', 'source_date', name='uq_attention_unique_finding'),
        sa.CheckConstraint("priority IN ('P1','P2','P3','V_VERIFY')", name='ck_attention_priority'),
        sa.CheckConstraint("status IN ('OPEN','IN_REVIEW','NEEDS_DATA','RESOLVED')", name='ck_attention_status'),
    )
    for col in ('organization_id', 'investor_id', 'advisor_id'):
        op.create_index('ix_attention_cases_'+col,'attention_cases',[col])
    op.create_table('advice_records',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('investor_id', sa.String(40), sa.ForeignKey('investors.id'), nullable=False),
        sa.Column('advisor_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('alert_id', sa.String(36), sa.ForeignKey('attention_cases.id'), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('recommendation', sa.Text(), nullable=False),
        sa.Column('rationale', sa.Text(), nullable=False),
        sa.Column('assumptions', sa.Text()),
        sa.Column('evidence_source_row_ids', sa.JSON(), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('submitted_at', sa.DateTime(timezone=True)),
        sa.Column('decided_at', sa.DateTime(timezone=True)),
        sa.Column('decided_by', sa.String(36), sa.ForeignKey('users.id')),
        sa.Column('decision_note', sa.Text()),
        sa.Column('supersedes_id', sa.String(36), sa.ForeignKey('advice_records.id')),
        sa.CheckConstraint("status IN ('DRAFT','SUBMITTED','APPROVED','REJECTED')", name='ck_advice_status'),
    )
    for col in ('organization_id','investor_id','advisor_id','alert_id'):
        op.create_index('ix_advice_records_'+col,'advice_records',[col])
    op.create_table('follow_up_tasks',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('investor_id', sa.String(40), sa.ForeignKey('investors.id'), nullable=False),
        sa.Column('advice_id', sa.String(36), sa.ForeignKey('advice_records.id'), nullable=False),
        sa.Column('owner_id', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('title', sa.String(200), nullable=False),
        sa.Column('due_date', sa.Date(), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('completion_note', sa.Text()),
        sa.Column('evidence_type', sa.String(32)),
        sa.Column('evidence_reference', sa.String(500)),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('completed_at', sa.DateTime(timezone=True)),
        sa.CheckConstraint("status IN ('OPEN','IN_PROGRESS','DONE','CANNOT_VERIFY')", name='ck_follow_up_status'),
    )
    for col in ('organization_id','investor_id','advice_id','owner_id'):
        op.create_index('ix_follow_up_tasks_'+col,'follow_up_tasks',[col])


def downgrade():
    for table,cols in (
        ('follow_up_tasks',('organization_id','investor_id','advice_id','owner_id')),
        ('advice_records',('organization_id','investor_id','advisor_id','alert_id')),
        ('attention_cases',('organization_id','investor_id','advisor_id')),
    ):
        for col in cols:
            op.drop_index('ix_'+table+'_'+col,table_name=table)
        op.drop_table(table)
