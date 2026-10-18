"""Evidence review and actual pilot session measurements."""
from alembic import op
import sqlalchemy as sa
revision='0012_evidence_pilot'
down_revision='0011_advisor_workflow_v4'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('review_evidence',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('investor_id',sa.String(40),sa.ForeignKey('investors.id'),nullable=False),
        sa.Column('advisor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('kind',sa.String(20),nullable=False),sa.Column('status',sa.String(20),nullable=False),
        sa.Column('payload',sa.JSON(),nullable=False),sa.Column('payload_sha256',sa.String(64),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),sa.Column('approved_at',sa.DateTime(timezone=True)),sa.Column('approval_note',sa.Text()))
    op.create_index('ix_evidence_org','review_evidence',['organization_id'])
    op.create_index('ix_evidence_client','review_evidence',['investor_id'])
    op.create_table('pilot_sessions',sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('advisor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('investor_id',sa.String(40),sa.ForeignKey('investors.id'),nullable=False),
        sa.Column('case_id',sa.String(36),sa.ForeignKey('attention_cases.id')),
        sa.Column('started_at',sa.DateTime(timezone=True),nullable=False),sa.Column('finished_at',sa.DateTime(timezone=True)),
        sa.Column('elapsed_seconds',sa.Integer()),sa.Column('outcome',sa.String(30)),sa.Column('baseline_seconds',sa.Integer()))
    op.create_index('ix_pilot_org','pilot_sessions',['organization_id'])
    op.create_index('ix_pilot_advisor','pilot_sessions',['advisor_id'])

def downgrade():
    op.drop_table('pilot_sessions');op.drop_table('review_evidence')
