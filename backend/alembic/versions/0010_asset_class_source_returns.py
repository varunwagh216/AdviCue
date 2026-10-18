"""Evidence-gated asset-class return observations for optional proxy gap explanation.

Revision ID: 0010_asset_class_returns
Revises: 0009_data_verification
"""
from alembic import op
import sqlalchemy as sa

revision='0010_asset_class_returns'
down_revision='0009_data_verification'
branch_labels=None
depends_on=None

def upgrade():
    op.create_table('asset_class_return_observations',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('asset_class',sa.String(100),nullable=False),
        sa.Column('month_date',sa.Date,nullable=False),
        sa.Column('reported_return_pct',sa.Numeric(12,6),nullable=False),
        sa.Column('source_reference',sa.String(300),nullable=False),
        sa.Column('source_filename',sa.String(200),nullable=False),
        sa.Column('file_sha256',sa.String(64),nullable=False),
        sa.Column('source_row_number',sa.Integer,nullable=False),
        sa.Column('imported_by',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('created_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('organization_id','asset_class','month_date',name='uq_org_class_return_month'))
    op.create_index('ix_asset_class_returns_org','asset_class_return_observations',['organization_id'])

def downgrade():
    op.drop_index('ix_asset_class_returns_org',table_name='asset_class_return_observations')
    op.drop_table('asset_class_return_observations')
