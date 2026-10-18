"""Optional advisor self-finalization and configurable organizational approval.

Revision ID: 0006_advisor_policy
Revises: 0005_phase78
"""
from alembic import op
import sqlalchemy as sa

revision = "0006_advisor_policy"
down_revision = "0005_phase78"
branch_labels = None
depends_on = None

def upgrade():
    with op.batch_alter_table("organizations") as batch:
        batch.add_column(sa.Column("approval_required",sa.Boolean(),nullable=False,server_default=sa.false()))

def downgrade():
    with op.batch_alter_table("organizations") as batch:
        batch.drop_column("approval_required")
