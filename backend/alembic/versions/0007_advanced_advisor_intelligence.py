"""Advanced investor intelligence fields and human-approved promises.

Revision ID: 0007_advisor_intelligence
Revises: 0006_advisor_policy
"""
from alembic import op
import sqlalchemy as sa
revision='0007_advisor_intelligence'
down_revision='0006_advisor_policy'
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table('investors') as b:
        b.add_column(sa.Column('advisor_preferences',sa.JSON(),nullable=True))
    with op.batch_alter_table('holdings') as b:
        b.add_column(sa.Column('purchase_date_confidence',sa.String(25),nullable=False,server_default='SOURCE_UNVERIFIED'))
    with op.batch_alter_table('investment_transactions') as b:
        b.add_column(sa.Column('date_confidence',sa.String(25),nullable=False,server_default='SOURCE_UNVERIFIED'))
        b.add_column(sa.Column('unit_price_confidence',sa.String(25),nullable=False,server_default='UNKNOWN'))
    with op.batch_alter_table('advice_records') as b:
        b.add_column(sa.Column('expected_outcome',sa.Text(),nullable=True))
        b.add_column(sa.Column('review_date',sa.Date(),nullable=True))
        b.add_column(sa.Column('review_trigger',sa.String(300),nullable=True))
    with op.batch_alter_table('meeting_notes') as b:
        b.add_column(sa.Column('approved_preferences',sa.JSON(),nullable=True))
    op.create_table('commitment_checks',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False,index=True),
        sa.Column('investor_id',sa.String(40),sa.ForeignKey('investors.id'),nullable=False,index=True),
        sa.Column('advisor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('meeting_id',sa.String(36),sa.ForeignKey('meeting_notes.id'),nullable=False,index=True),
        sa.Column('metric',sa.String(36),nullable=False),
        sa.Column('comparator',sa.String(3),nullable=False),
        sa.Column('target_pct',sa.Numeric(7,2),nullable=False),
        sa.Column('due_date',sa.Date(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))

def downgrade():
    op.drop_table('commitment_checks')
    with op.batch_alter_table('meeting_notes') as b:b.drop_column('approved_preferences')
    with op.batch_alter_table('advice_records') as b:
        b.drop_column('review_trigger');b.drop_column('review_date');b.drop_column('expected_outcome')
    with op.batch_alter_table('investment_transactions') as b:
        b.drop_column('unit_price_confidence');b.drop_column('date_confidence')
    with op.batch_alter_table('holdings') as b:b.drop_column('purchase_date_confidence')
    with op.batch_alter_table('investors') as b:b.drop_column('advisor_preferences')
