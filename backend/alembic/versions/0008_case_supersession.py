"""Preserve historical review cases while displaying one current case per investor.

Revision ID: 0008_case_supersession
Revises: 0007_advisor_intelligence
"""
from alembic import op
import sqlalchemy as sa

revision = '0008_case_supersession'
down_revision = '0007_advisor_intelligence'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('attention_cases') as b:
        b.add_column(sa.Column('superseded_by_id', sa.String(36), nullable=True))
    conn = op.get_bind()
    rows = conn.execute(sa.text('''
        SELECT id, organization_id, investor_id, source_date, rule_id, priority, created_at
        FROM attention_cases
    ''')).mappings().all()
    grouped = {}
    for row in rows:
        grouped.setdefault((row['organization_id'], row['investor_id']), []).append(row)
    priority = {'P1': 3, 'P2': 2, 'P3': 1, 'V_VERIFY': 0}
    for cases in grouped.values():
        if len(cases) < 2:
            continue
        canonical = max(cases, key=lambda row: (
            str(row['source_date'] or ''),
            bool((row['rule_id'] or '').startswith('PAT_PEER_')),
            priority.get(row['priority'], 0),
            str(row['created_at'] or ''), str(row['id']),
        ))
        for case in cases:
            if case['id'] != canonical['id']:
                conn.execute(sa.text('UPDATE attention_cases SET superseded_by_id=:next WHERE id=:old'),
                             {'next': canonical['id'], 'old': case['id']})
    # Application maintains this pointer for future scans; no records are deleted.


def downgrade():
    with op.batch_alter_table('attention_cases') as b:
        b.drop_column('superseded_by_id')
