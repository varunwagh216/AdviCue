"""Advanced-regression contracts for review supersession and trusted source joins."""
from datetime import date, datetime, timezone
from decimal import Decimal
from types import SimpleNamespace as NS

from sqlalchemy import select

from app.core.database import SessionLocal
from app.engines.advanced import advice_outcome
from app.models import AttentionCase, PatternRun, DetectedPattern, Investor, Holding, InvestmentTransaction
from app.services.attention import consolidate_attention_cases
from app.services.reconciliation import reconcile_transactions_holdings
from tests.conftest import sign_in
from tests.test_phase34 import seed_test_group


def test_reconciliation_distinguishes_class_matching_from_instrument_naming():
    h=[NS(investor_id='I1',asset_class='Fixed Deposit',instrument_name='Bank ABC FD',
          current_value=Decimal('1000'),source_row_id='h1')]
    tx=[NS(investor_id='I1',asset_class='Fixed Deposit',instrument_name='ABC deposit SIP',
           type='SIP',amount=Decimal('200'),source_row_id='t1',possible_duplicate=False,
           date_confidence='QUARANTINED_AMBIGUOUS',unit_price_confidence='UNRELIABLE_AMOUNT_AUTHORITATIVE'),
        NS(investor_id='I1',asset_class='Fixed Deposit',instrument_name='ABC deposit SIP',
           type='SIP',amount=Decimal('200'),source_row_id='t2',possible_duplicate=True,
           date_confidence='EXACT_ISO_OR_EXCEL',unit_price_confidence='UNKNOWN')]
    result=reconcile_transactions_holdings(h,tx)
    assert result['matched_investor_class_pairs']==1
    assert result['matched_fund_names_within_paired_classes']==0
    assert result['excluded_duplicate_copies']==1
    assert result['quarantined_date_rows']==1
    assert result['unreliable_sip_unit_price_rows']==1
    assert 'not proof' in result['note']


def test_reconciliation_endpoint_requires_authorized_operator(client):
    sign_in(client)
    # Ordinary advisors may read assigned clients, but never see organization-wide
    # transaction joins across colleagues' investor records.
    result=client.get('/api/v1/imports/reconciliation/summary')
    assert result.status_code==403


def test_superseded_cases_are_hidden_from_current_queue_but_retained(client):
    seed_test_group()
    token=sign_in(client,'supervisor@advicue.local')['csrf_token']
    assert client.post('/api/v1/patterns/run',headers={
        'Origin':'http://localhost:5173','X-CSRF-Token':token}).status_code==200
    with SessionLocal() as db:
        current=db.scalar(select(AttentionCase).where(AttentionCase.investor_id=='PAT-0'))
        assert current is not None
        legacy=AttentionCase(organization_id=current.organization_id,
            investor_id=current.investor_id,advisor_id=current.advisor_id,
            pattern_id=current.pattern_id,rule_id='LEGACY_SAME_INVESTOR',
            rule_version='1.0',source_date=current.source_date,priority='P2',
            title='Historic legacy review',reason='Legacy evidence kept for audit',
            suggested_action='Review mandate',evidence_source_row_ids=[])
        db.add(legacy)
        db.flush()
        legacy_id=legacy.id
        stats=consolidate_attention_cases(db,'org-a','supervisor-a')
        db.commit()
        assert stats['supersession_links_changed']==1
        assert db.get(AttentionCase,legacy_id).superseded_by_id==current.id
        assert consolidate_attention_cases(db,'org-a')['supersession_links_changed']==0
    sign_in(client)
    current_queue=client.get('/api/v1/attention')
    assert current_queue.status_code==200
    assert len([row for row in current_queue.json()['items'] if row['investor_id']=='PAT-0'])==1
    history=client.get('/api/v1/attention?include_history=true')
    assert history.status_code==200
    assert len([row for row in history.json()['items'] if row['investor_id']=='PAT-0'])==2
    assert client.get(f'/api/v1/attention/{legacy_id}').status_code==200
    advisor=sign_in(client)
    action=client.post(f'/api/v1/attention/{legacy_id}/actions',headers={
        'Origin':'http://localhost:5173','X-CSRF-Token':advisor['csrf_token']},
        json={'action':'START_REVIEW','note':''})
    assert action.status_code==409


def test_advice_observations_have_pre_post_context_without_causal_claims():
    obj=NS(status='APPROVED',decided_at=datetime(2026,3,15,tzinfo=timezone.utc),submitted_at=None)
    def snap(month,p,b):
        return NS(snapshot_date=date(2026,month,1),
            source_reported_portfolio_return_pct=Decimal(p),
            source_reported_benchmark_return_pct=Decimal(b),
            source_row_id=f's{month}')
    result=advice_outcome(obj,[snap(1,'0','2'),snap(2,'1','2'),snap(3,'0','2'),snap(4,'2','2')])
    assert result['status']=='OBSERVATIONAL_ONLY'
    assert result['baseline_reported_comparison']['observed_months']==3
    assert result['reported_comparison']['observed_months']==1
    assert result['reported_mean_monthly_gap_change_pp'] is not None
    assert result['execution_verified'] is False
    assert 'NOT evidence' in result['reason']


def test_commitment_at_due_date_ignores_later_holding_changes():
    from app.engines.advanced import check_commitment_against_dated_holdings
    commitment=NS(metric='fixed_deposit_pct',comparator='>=',target_pct=Decimal('50'),
                  due_date=date(2026,7,31))
    note=NS(approved_at=datetime(2026,6,30,tzinfo=timezone.utc))
    # Genuine as-of-date observations are required; a later date may not cure a
    # failed July commitment or establish that it was met on July 31.
    def hold(day,value):
        return NS(as_of_date=day,asset_class='Fixed Deposit',current_value=Decimal(value),
                  source_row_id=f'h-{day}')
    def eq(day,value):
        return NS(as_of_date=day,asset_class='Direct Equity',current_value=Decimal(value),
                  source_row_id=f'e-{day}')
    July=date(2026,7,31)
    late=date(2026,8,31)
    failed=check_commitment_against_dated_holdings(commitment,note,
                      [hold(July,40),eq(July,60),hold(late,100)])
    assert failed['status']=='BROKEN'
    assert failed['observed_date']=='2026-07-31'
    missing=check_commitment_against_dated_holdings(commitment,note,
                      [hold(late,100)])
    assert missing['status']=='NOT_ASSESSABLE'
    kept=check_commitment_against_dated_holdings(commitment,note,[hold(July,60),eq(July,40)])
    assert kept['status']=='KEPT'


def test_sourced_asset_class_proxy_needs_all_months_and_reconciles():
    from app.engines.advanced import sourced_class_return_proxy
    comparison={'sum_monthly_gap_pp':'-4.00','months':[{'date':'2026-01-01'}, {'date':'2026-02-01'}]}
    exposure={'status':'ALLOCATION_ONLY','items':[
        {'asset_class':'Debt Mutual Fund','weight_difference_pp':'25.00'},
        {'asset_class':'Direct Equity','weight_difference_pp':'-25.00'}]}
    def row(cls,month,pct):
        return NS(asset_class=cls,month_date=date(2026,month,1),reported_return_pct=Decimal(pct),
                  source_reference=f'provider-file-{month}',file_sha256='b'*64)
    incomplete=sourced_class_return_proxy(comparison,exposure,[row('Debt Mutual Fund',1,2)])
    assert incomplete['status']=='NO_COMPARABLE_CLASS_RETURN_EVIDENCE'
    result=sourced_class_return_proxy(comparison,exposure,[
        row('Debt Mutual Fund',1,2),row('Debt Mutual Fund',2,2),
        row('Direct Equity',1,4),row('Direct Equity',2,4)])
    assert result['status']=='SOURCED_ALLOCATION_PROXY_NOT_CAUSAL'
    summed=sum((Decimal(x['proxy_contribution_pp']) for x in result['contributions']),Decimal('0'))
    assert summed+Decimal(result['unexplained_gap_pp'])==Decimal(result['reported_summed_gap_pp'])
    assert 'not actual historic client weights' in result['note'].lower()


def test_asset_class_csv_atomic_validation_and_authorization(client):
    from app.services.class_return_import import parse_class_returns, ClassReturnImportError
    import pytest
    with pytest.raises(ClassReturnImportError):
        parse_class_returns(b'month,asset_class,return_pct,source_reference\n2026-01,FD,nan,unverified\n')
    with pytest.raises(ClassReturnImportError):
        parse_class_returns(b'month,asset_class,return_pct,source_reference\n2026-01,FD,2,x\n2026-01,FD,5,y\n')
    sign_in(client)
    sample=b'month,asset_class,return_pct,source_reference\n2026-01,Direct Equity,2.3,Source index sheet A\n'
    assert client.get('/api/v1/imports/asset-returns/summary').status_code==403
    unauthorized=client.post('/api/v1/imports/asset-returns/upload',
        headers={'Origin':'http://localhost:5173'},files={'file':('returns.csv',sample,'text/csv')})
    assert unauthorized.status_code in (403,422)
    token=sign_in(client,'supervisor@advicue.local')['csrf_token']
    headers={'Origin':'http://localhost:5173','X-CSRF-Token':token}
    imported=client.post('/api/v1/imports/asset-returns/upload',headers=headers,
        files={'file':('returns.csv',sample,'text/csv')})
    assert imported.status_code==201,imported.text
    assert imported.json()['status']=='IMPORTED_UNVERIFIED'
    summary=client.get('/api/v1/imports/asset-returns/summary')
    assert summary.status_code==200 and summary.json()['observations']==1
    duplicate=client.post('/api/v1/imports/asset-returns/upload',headers=headers,
        files={'file':('returns.csv',sample,'text/csv')})
    assert duplicate.status_code==422
    assert client.get('/api/v1/imports/asset-returns/summary').json()['observations']==1


def test_future_due_promise_cannot_be_marked_kept_in_advance():
    from app.engines.advanced import check_commitment_against_dated_holdings
    due=date(2027,7,31)
    promise=NS(metric='fixed_deposit_pct',comparator='>=',target_pct=Decimal('50'),due_date=due)
    note=NS(approved_at=datetime(2027,1,1,tzinfo=timezone.utc))
    h=[NS(as_of_date=due,asset_class='Fixed Deposit',current_value=Decimal(100),source_row_id='future')]
    outcome=check_commitment_against_dated_holdings(promise,note,h,as_of_today=date(2027,4,1))
    assert outcome['status']=='ON_TRACK'
