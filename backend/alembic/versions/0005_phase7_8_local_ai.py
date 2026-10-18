"""Phase 7 local AI/meeting notes and Phase 8 security audit trail integration.

Revision ID: 0005_phase78
Revises: 0004_phase56
"""
from alembic import op
import sqlalchemy as sa
revision = '0005_phase78'
down_revision = '0004_phase56'
branch_labels = None
depends_on = None

def upgrade():
    op.create_table('local_ai_briefs',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('investor_id',sa.String(40),sa.ForeignKey('investors.id'),nullable=False),
        sa.Column('created_by',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('model_name',sa.String(120),nullable=False),
        sa.Column('summary',sa.Text(),nullable=False),
        sa.Column('review_questions',sa.JSON(),nullable=False),
        sa.Column('cited_fact_ids',sa.JSON(),nullable=False),
        sa.Column('fact_snapshot',sa.JSON(),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False))
    op.create_index('ix_local_ai_briefs_organization_id','local_ai_briefs',['organization_id'])
    op.create_index('ix_local_ai_briefs_investor_id','local_ai_briefs',['investor_id'])
    op.create_table('meeting_notes',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('investor_id',sa.String(40),sa.ForeignKey('investors.id'),nullable=False),
        sa.Column('advisor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('input_method',sa.String(20),nullable=False),
        sa.Column('recording_consent_at',sa.DateTime(timezone=True)),
        sa.Column('audio_sha256',sa.String(64)),
        sa.Column('transcript',sa.Text(),nullable=False),
        sa.Column('status',sa.String(20),nullable=False),
        sa.Column('extracted_draft',sa.JSON()),
        sa.Column('approved_summary',sa.Text()),
        sa.Column('approved_commitments',sa.JSON()),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.Column('approved_at',sa.DateTime(timezone=True)),
        sa.Column('approved_by',sa.String(36),sa.ForeignKey('users.id')),
        sa.CheckConstraint("status IN ('DRAFT','APPROVED')",name='ck_meeting_note_status'))
    op.create_index('ix_meeting_notes_organization_id','meeting_notes',['organization_id'])
    op.create_index('ix_meeting_notes_investor_id','meeting_notes',['investor_id'])
    # SQLite supports adding a nullable REFERENCES column through SQL; Alembic's
    # generic add_column attempts a separate ALTER CONSTRAINT (unsupported).
    if op.get_bind().dialect.name == 'sqlite':
        op.execute('ALTER TABLE advice_records ADD COLUMN source_meeting_id VARCHAR(36) REFERENCES meeting_notes(id)')
    else:
        op.add_column('advice_records', sa.Column('source_meeting_id',sa.String(36),sa.ForeignKey('meeting_notes.id'),nullable=True))

def downgrade():
    with op.batch_alter_table('advice_records') as batch:
        batch.drop_column('source_meeting_id')
    op.drop_index('ix_meeting_notes_investor_id','meeting_notes')
    op.drop_index('ix_meeting_notes_organization_id','meeting_notes')
    op.drop_table('meeting_notes')
    op.drop_index('ix_local_ai_briefs_investor_id','local_ai_briefs')
    op.drop_index('ix_local_ai_briefs_organization_id','local_ai_briefs')
    op.drop_table('local_ai_briefs')
