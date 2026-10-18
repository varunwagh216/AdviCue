"""Phase 2: staged workbook imports, quality issues, holdings, transactions and snapshots.

Revision ID: 0002_phase2
Revises: 0001_phase1
"""
from alembic import op
import sqlalchemy as sa

revision = '0002_phase2'
down_revision = '0001_phase1'
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table('users') as batch:
        batch.add_column(sa.Column('external_advisor_code', sa.String(32), nullable=True))
    with op.batch_alter_table('investors') as batch:
        batch.add_column(sa.Column('source_advisor_code', sa.String(32)))
        batch.add_column(sa.Column('age', sa.Integer()))
        batch.add_column(sa.Column('primary_goal', sa.String(120)))
        batch.add_column(sa.Column('goal_target_amount', sa.Numeric(22,2)))
        batch.add_column(sa.Column('goal_target_date', sa.Date()))
        batch.add_column(sa.Column('onboarding_date', sa.Date()))
        batch.add_column(sa.Column('effective_date', sa.Date()))
        batch.add_column(sa.Column('city', sa.String(100)))
        batch.add_column(sa.Column('source_row_id', sa.String(36)))

    op.create_table('import_batches',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('organization_id', sa.String(36), sa.ForeignKey('organizations.id'), nullable=False),
        sa.Column('uploaded_by', sa.String(36), sa.ForeignKey('users.id'), nullable=False),
        sa.Column('filename', sa.String(240), nullable=False),
        sa.Column('file_sha256', sa.String(64), nullable=False),
        sa.Column('status', sa.String(20), nullable=False),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('committed_at', sa.DateTime(timezone=True)),
        sa.Column('total_rows', sa.Integer(), nullable=False),
        sa.Column('error_count', sa.Integer(), nullable=False),
        sa.Column('warning_count', sa.Integer(), nullable=False),
        sa.Column('sheet_counts', sa.JSON(), nullable=False),
        sa.UniqueConstraint('organization_id','file_sha256',name='uq_batch_org_hash'))
    op.create_index('ix_import_batches_organization_id','import_batches',['organization_id'])
    op.create_table('source_rows',
        sa.Column('id', sa.String(36), primary_key=True),
        sa.Column('batch_id', sa.String(36), sa.ForeignKey('import_batches.id',ondelete='CASCADE'), nullable=False),
        sa.Column('sheet_name', sa.String(40), nullable=False),
        sa.Column('row_number', sa.Integer(), nullable=False),
        sa.Column('raw_data', sa.JSON(), nullable=False),
        sa.Column('normalized_data', sa.JSON(), nullable=False),
        sa.Column('accepted',sa.Boolean(), nullable=False),
        sa.UniqueConstraint('batch_id','sheet_name','row_number',name='uq_source_row_position'))
    op.create_index('ix_source_rows_batch_id','source_rows',['batch_id'])
    op.create_table('data_quality_issues',
        sa.Column('id', sa.String(36),primary_key=True),
        sa.Column('batch_id',sa.String(36),sa.ForeignKey('import_batches.id',ondelete='CASCADE'),nullable=False),
        sa.Column('source_row_id',sa.String(36),sa.ForeignKey('source_rows.id',ondelete='CASCADE')),
        sa.Column('sheet_name',sa.String(40),nullable=False),
        sa.Column('row_number',sa.Integer(),nullable=False),
        sa.Column('field_name',sa.String(64)),
        sa.Column('severity',sa.String(8),nullable=False),
        sa.Column('code',sa.String(48),nullable=False),
        sa.Column('message',sa.String(350),nullable=False))
    op.create_index('ix_data_quality_issues_batch_id','data_quality_issues',['batch_id'])
    with op.batch_alter_table('investors') as batch:
        batch.create_foreign_key('fk_investor_source_row','source_rows',['source_row_id'],['id'])
    op.create_table('holdings',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('investor_id',sa.String(40),sa.ForeignKey('investors.id'),nullable=False),
        sa.Column('source_row_id',sa.String(36),sa.ForeignKey('source_rows.id'),nullable=False,unique=True),
        sa.Column('external_holding_id',sa.String(40),nullable=False),
        sa.Column('as_of_date',sa.Date(),nullable=False),
        sa.Column('asset_class',sa.String(80),nullable=False),
        sa.Column('instrument_name',sa.String(200),nullable=False),
        sa.Column('units',sa.Numeric(22,6)),
        sa.Column('average_purchase_price',sa.Numeric(22,6)),
        sa.Column('purchase_date',sa.Date()),
        sa.Column('current_price',sa.Numeric(22,6)),
        sa.Column('current_value',sa.Numeric(22,2),nullable=False))
    for col in ('organization_id','investor_id'):
        op.create_index(f'ix_holdings_{col}','holdings',[col])
    op.create_table('investment_transactions',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('investor_id',sa.String(40),sa.ForeignKey('investors.id'),nullable=False),
        sa.Column('source_row_id',sa.String(36),sa.ForeignKey('source_rows.id'),nullable=False,unique=True),
        sa.Column('external_transaction_id',sa.String(40),nullable=False),
        sa.Column('date',sa.Date(),nullable=False),
        sa.Column('type',sa.String(60),nullable=False),
        sa.Column('instrument_name',sa.String(200),nullable=False),
        sa.Column('asset_class',sa.String(80),nullable=False),
        sa.Column('units',sa.Numeric(22,6)),
        sa.Column('price_per_unit',sa.Numeric(22,6)),
        sa.Column('amount',sa.Numeric(22,2),nullable=False),
        sa.Column('possible_duplicate',sa.Boolean(),nullable=False),
        sa.Column('external_flow_status',sa.String(28),nullable=False))
    for col in ('organization_id','investor_id'):
        op.create_index(f'ix_investment_transactions_{col}','investment_transactions',[col])
    op.create_table('performance_snapshots',
        sa.Column('id',sa.String(36),primary_key=True),
        sa.Column('organization_id',sa.String(36),sa.ForeignKey('organizations.id'),nullable=False),
        sa.Column('investor_id',sa.String(40),sa.ForeignKey('investors.id'),nullable=False),
        sa.Column('source_row_id',sa.String(36),sa.ForeignKey('source_rows.id'),nullable=False,unique=True),
        sa.Column('snapshot_date',sa.Date(),nullable=False),
        sa.Column('portfolio_value',sa.Numeric(22,2),nullable=False),
        sa.Column('benchmark_index_value',sa.Numeric(22,6)),
        sa.Column('source_reported_portfolio_return_pct',sa.Numeric(10,4)),
        sa.Column('source_reported_benchmark_return_pct',sa.Numeric(10,4)),
        sa.Column('return_verification_status',sa.String(30),nullable=False))
    for col in ('organization_id','investor_id'):
        op.create_index(f'ix_performance_snapshots_{col}','performance_snapshots',[col])


def downgrade():
    op.drop_table('performance_snapshots')
    op.drop_table('investment_transactions')
    op.drop_table('holdings')
    with op.batch_alter_table('investors') as batch:
        batch.drop_constraint('fk_investor_source_row',type_='foreignkey')
    op.drop_table('data_quality_issues')
    op.drop_table('source_rows')
    op.drop_table('import_batches')
    with op.batch_alter_table('investors') as batch:
        for c in ['source_row_id','city','effective_date','onboarding_date','goal_target_date','goal_target_amount','primary_goal','age','source_advisor_code']:
            batch.drop_column(c)
    with op.batch_alter_table('users') as batch:
        batch.drop_column('external_advisor_code')
