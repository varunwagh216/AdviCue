"""Permit distinct provenance-review cases without fictitious pattern membership.

Revision ID: 0009_data_verification
Revises: 0008_case_supersession
"""
from alembic import op
import sqlalchemy as sa

revision='0009_data_verification'
down_revision='0008_case_supersession'
branch_labels=None
depends_on=None


def upgrade():
    # SQLite requires table recreation when modifying nullable foreign keys.
    with op.batch_alter_table('attention_cases') as b:
        b.alter_column('pattern_id', existing_type=sa.String(36), nullable=True)


def downgrade():
    # First archive/delete data-only review cases before downgrading, otherwise
    # making the original pattern FK mandatory would destroy their meaning.
    conn=op.get_bind()
    count=conn.execute(sa.text('SELECT COUNT(*) FROM attention_cases WHERE pattern_id IS NULL')).scalar()
    if count:
        raise RuntimeError('Data-verification cases exist; a destructive downgrade is refused')
    with op.batch_alter_table('attention_cases') as b:
        b.alter_column('pattern_id', existing_type=sa.String(36), nullable=False)
