"""meeting tasks, measurable advice and saved goal plans."""
from alembic import op
import sqlalchemy as sa
revision='0011_advisor_workflow_v4'
down_revision='0010_asset_class_returns'
branch_labels=None
depends_on=None

def upgrade():
    with op.batch_alter_table('follow_up_tasks') as b:
        b.alter_column('advice_id',existing_type=sa.String(36),nullable=True)
        b.add_column(sa.Column('source_meeting_id',sa.String(36),nullable=True))
        b.create_foreign_key('fk_task_meeting','meeting_notes',['source_meeting_id'],['id'])
    op.add_column('advice_records',sa.Column('outcome_rule',sa.JSON(),nullable=True))
    op.create_table('goal_plans',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('investor_id',sa.String(40),sa.ForeignKey('investors.id'),nullable=False),
        sa.Column('advisor_id',sa.String(36),sa.ForeignKey('users.id'),nullable=False),
        sa.Column('principal',sa.Numeric(22,2),nullable=False),
        sa.Column('monthly_contribution',sa.Numeric(22,2),nullable=False),
        sa.Column('as_of_date',sa.Date(),nullable=False),
        sa.Column('annual_rates',sa.JSON(),nullable=False),
        sa.Column('updated_at',sa.DateTime(timezone=True),nullable=False),
        sa.UniqueConstraint('organization_id','investor_id',name='uq_goal_plan_investor'))

def downgrade():
    # Meeting-origin tasks cannot be converted into fabricated advice links.
    bind=op.get_bind()
    if bind.execute(sa.text('SELECT COUNT(*) FROM follow_up_tasks WHERE advice_id IS NULL')).scalar():
        raise RuntimeError('Export meeting-origin tasks before downgrading .')
    op.drop_table('goal_plans')
    op.drop_column('advice_records','outcome_rule')
    with op.batch_alter_table('follow_up_tasks') as b:
        b.drop_constraint('fk_task_meeting',type_='foreignkey')
        b.drop_column('source_meeting_id')
        b.alter_column('advice_id',existing_type=sa.String(36),nullable=False)
