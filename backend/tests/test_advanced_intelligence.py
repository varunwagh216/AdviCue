"""Investor intelligence v2: real computations, traceability and privacy regression."""
from __future__ import annotations
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS
import pytest
from sqlalchemy import select

from app.engines.advanced import (reported_comparison, priority_components, allocation_peer_explanation,
                                  attributable_gap, advice_outcome, behaviour_signals)
from app.services.trust import date_classification, transaction_unit_quality, sip_recurrence_days
from app.core.database import SessionLocal
from app.models import (SourceRow, Holding, Investor, PerformanceSnapshot, AdviceRecord, MeetingNote, CommitmentCheck)
from tests.conftest import sign_in
from tests.test_phase34 import seed_test_group


def snapshot(when, pr=None, bm=None):
    return NS(snapshot_date=date.fromisoformat(when),source_reported_portfolio_return_pct=pr,
              source_reported_benchmark_return_pct=bm,source_row_id='snapshot-'+when)


def test_reported_comparison_distinguishes_arithmetic_and_linked_gaps():
    c=reported_comparison([snapshot('2026-01-01','2','4'),snapshot('2026-02-01','1','3')])
    assert c['status']=='SOURCE_REPORTED_UNVERIFIED'
    assert c['observed_months']==2 and c['negative_months']==2
    assert c['sum_monthly_gap_pp']=='-4.00'
    assert c['reported_linked_gap_pp']=='-4.10'
    assert len(c['source_row_ids'])==2
    assert reported_comparison([snapshot('2026-01-01')])['status']=='NO_REPORTED_COMPARISON'


def test_unverified_class_returns_leave_full_gap_unattributed():
    cmp=reported_comparison([snapshot('2026-01-01','0','3')])
    exposure={'status':'ALLOCATION_ONLY','items':[
        {'asset_class':'Fixed Deposit','weight_difference_pp':'20.00'},
        {'asset_class':'Equity Mutual Fund','weight_difference_pp':'-20.00'}]}
    withheld=attributable_gap({},exposure,cmp)
    assert withheld['status']=='NO_CLASS_RETURN_EVIDENCE'
    assert withheld['unexplained_gap_pp']==cmp['reported_linked_gap_pp']
    partial=attributable_gap({},exposure,cmp,{'Fixed Deposit':'2'})
    assert partial['status']=='INCOMPLETE_CLASS_RETURN_EVIDENCE'
    full=attributable_gap({},exposure,cmp,{'Fixed Deposit':'2','Equity Mutual Fund':'8'})
    assert sum(Decimal(x['contribution_pp']) for x in full['contributions'])+Decimal(full['unexplained_gap_pp'])==Decimal(cmp['reported_linked_gap_pp'])


def test_priority_ranking_is_deterministic_and_explainable():
    many={'observed_months':11,'negative_months':11,'sum_monthly_gap_pp':'-22.42'}
    high=priority_components(many,'800000',date(2026,12,31),date(2026,7,31))
    assert high['band']=='P1' and high['components']['gap_points']==35
    low=priority_components({'observed_months':11,'negative_months':1,'sum_monthly_gap_pp':'-1.00'},'10000')
    assert low['band']=='P3'
    assert priority_components({'observed_months':3},'10000')['band']=='V_VERIFY'
    assert priority_components({'observed_months':0},'10000')['band']=='P2' # allocation-only review, not false performance claim


def test_peer_exposure_is_not_causal_attribution():
    def alloc(eq,fd):
        return {'status':'VALID','asset_classes':[{'asset_class':'Direct Equity','weight_pct':str(eq)},
                   {'asset_class':'Fixed Deposit','weight_pct':str(fd)}]}
    a=allocation_peer_explanation(alloc(0,55),[alloc(60,0),alloc(60,0),alloc(65,0)])
    assert a['status']=='ALLOCATION_ONLY'
    assert {x['asset_class']:x['weight_difference_pp'] for x in a['items']}['Direct Equity']=='-60.00'
    assert 'NOT a return attribution' in a['note']


def test_transaction_dates_are_cautiously_inferred_or_quarantined():
    rows=[NS(raw_data={'investor_id':'X','type':'SIP','date':f'2026-0{i}-04'}) for i in (1,2,3)]
    days=sip_recurrence_days(rows)
    assert days['X']=={4}
    assert date_classification('04-12-2026',expected_days=days['X'])=='INFERRED_DAY_FIRST'
    assert date_classification('05-06-2026',expected_days=days['X'])=='QUARANTINED_AMBIGUOUS'
    assert date_classification('2026-12-04',expected_days=days['X'])=='EXACT_ISO_OR_EXCEL'


def test_sip_units_are_not_used_when_inconsistent():
    assert transaction_unit_quality({'type':'SIP','units':'100','price_per_unit':'20','amount':'300'})=='UNRELIABLE_AMOUNT_AUTHORITATIVE'
    assert transaction_unit_quality({'type':'Redemption','units':'10','price_per_unit':'20','amount':'200'})=='MATCHED'


def test_behaviour_excludes_duplicate_and_quarantined_rows():
    def tx(i,kind,cls,when,amt,dup=False,conf='EXACT_ISO_OR_EXCEL'):
        return NS(investor_id=i,type=kind,asset_class=cls,date=date.fromisoformat(when),amount=Decimal(amt),
                  possible_duplicate=dup,date_confidence=conf,source_row_id=f'{i}{when}{amt}')
    rows=[tx('A','SIP','Fixed Deposit',f'2026-0{m}-01','100') for m in (1,2,3)]
    rows += [tx('A','SIP','Direct Equity','2026-03-01','300',dup=True),
             tx('A','SIP','Direct Equity','2026-04-01','300',conf='QUARANTINED_AMBIGUOUS')]
    signals=behaviour_signals(rows)
    assert len(signals)==1 and signals[0]['share_pct']=='100.00'


def test_post_advice_outcome_is_observational_only():
    obj=NS(status='APPROVED',decided_at=datetime(2026,1,15,tzinfo=timezone.utc),submitted_at=None)
    assert advice_outcome(obj,[snapshot('2026-01-01','1','2')])['status']=='NOT_ASSESSABLE'
    assessed=advice_outcome(obj,[snapshot('2026-02-01','1','2')])
    assert assessed['status']=='OBSERVATIONAL_ONLY'
    assert 'NOT evidence' in assessed['reason']


def test_financial_api_preserves_investor_scope_and_keeps_reported_data(client):
    sign_in(client)
    assert client.get('/api/v1/investors/B-001/analysis').status_code==404
    resp=client.get('/api/v1/investors/A-001/analysis')
    assert resp.status_code==200
    assert resp.json()['reported_comparison']['status']=='NO_REPORTED_COMPARISON'
    assert resp.json()['performance']['status']=='NOT_ASSESSABLE'
    assert client.get('/api/v1/insights/behaviour').status_code==200


def test_extended_advice_record_and_outcome_route(client):
    seed_test_group()
    supervisor=sign_in(client,'supervisor@advicue.local')
    headers={'Origin':'http://localhost:5173','X-CSRF-Token':supervisor['csrf_token']}
    assert client.post('/api/v1/patterns/run',headers=headers).status_code==200
    advisor=sign_in(client)
    headers={'Origin':'http://localhost:5173','X-CSRF-Token':advisor['csrf_token']}
    case=client.get('/api/v1/attention').json()['items'][0]
    created=client.post('/api/v1/advice',headers=headers,json={
        'alert_id':case['id'],'recommendation':'Review mandate in the next client meeting.',
        'rationale':'Same-date allocation warrants an investor mandate review.',
        'expected_outcome':'Confirm client liquidity requirements in the next review.',
        'review_date':'2027-01-01','review_trigger':'Client updates investment horizon'})
    assert created.status_code==201,created.text
    assert created.json()['review_date']=='2027-01-01'
    assert created.json()['expected_outcome'].startswith('Confirm client')
    outcome=client.get(f"/api/v1/advice/{created.json()['id']}/outcome")
    assert outcome.status_code==200
    assert outcome.json()['status']=='NOT_ASSESSABLE'


def test_meeting_preferences_and_checkable_promises_require_approval(client):
    from app.models import Investor
    from app.core.database import SessionLocal
    token=sign_in(client)['csrf_token']
    h={'Origin':'http://localhost:5173','X-CSRF-Token':token}
    note=client.post('/api/v1/meetings/notes',headers=h,json={
        'investor_id':'A-001','transcript':'Client wants cash for a house purchase and agreed to verify liquidity needs.'})
    assert note.status_code==201,note.text
    nid=note.json()['id']
    rejected=client.post(f'/api/v1/meetings/{nid}/commitment-checks',headers=h,json={
        'metric':'equity_pct','comparator':'>=','target_pct':15,'due_date':'2027-06-01'})
    assert rejected.status_code==422
    approval=client.post(f'/api/v1/meetings/{nid}/approve',headers=h,json={
        'summary':'Reviewed house purchase liquidity needs with the investor.',
        'commitments':['Confirm target equity allocation by follow-up'],
        'preferences':{'liquidity_needs':'House purchase within twelve months'}})
    assert approval.status_code==200,approval.text
    with SessionLocal() as db:
        investor=db.get(Investor,'A-001')
        assert investor.advisor_preferences['values']['liquidity_needs'].startswith('House')
    created=client.post(f'/api/v1/meetings/{nid}/commitment-checks',headers=h,json={
        'metric':'equity_pct','comparator':'>=','target_pct':15,'due_date':'2027-06-01'})
    assert created.status_code==201,created.text
    response=client.get('/api/v1/investors/A-001/commitment-checks')
    assert response.status_code==200
    assert response.json()['items'][0]['status']=='NOT_ASSESSABLE'
    sign_in(client,'b@advicue.local')
    assert client.get('/api/v1/investors/A-001/commitment-checks').status_code==404


def test_reference_workbook_reported_gap_11_of_11():
    from app.services.importer import read_rows
    workbook=Path(__file__).resolve().parents[2]/'sample_data'/'Transaction History Investor.xlsx'
    sheets,_=read_rows(workbook.read_bytes())
    rows=[]
    for rn,raw in sheets['performance_history']:
        if raw['investor_id']=='INV0009':
            rows.append(snapshot(raw['snapshot_date'],raw['portfolio_return_pct'],raw['benchmark_return_pct']))
    cmp=reported_comparison(rows)
    assert cmp['observed_months']==11 and cmp['negative_months']==11
    assert cmp['sum_monthly_gap_pp']=='-22.42'


def test_number_safe_fact_templates_reject_hallucinations():
    from app.ai.fact_templates import render_fact_template,UnverifiedNumericClaim
    allowed={'FD_PCT':'55.00','GOAL_DATE':'2029-09-01'}
    assert render_fact_template('Deposit share: [[FD_PCT]] percent.',allowed)=='Deposit share: 55.00 percent.'
    with pytest.raises(UnverifiedNumericClaim):render_fact_template('Deposit share 90 percent.',allowed)
    with pytest.raises(UnverifiedNumericClaim):render_fact_template('Target: [[UNKNOWN]]',allowed)
    with pytest.raises(UnverifiedNumericClaim):render_fact_template('FY2026 target.',allowed)


def test_general_peer_clusters_discover_non_fd_anomaly():
    from app.engines.patterns import detect_general_peer_clusters
    inv=[NS(id=f'P-{i}',risk_profile='Moderate',advisor_id=f'ADV{i%3}',source_advisor_code=f'ADV{i%3}') for i in range(14)]
    holds=[]
    for i in range(14):
        for cls,value in ([('Gold ETF',80),('Direct Equity',20)] if i<6 else [('Gold ETF',0),('Direct Equity',100)]):
            holds.append(NS(investor_id=inv[i].id,source_row_id=f'{i}:{cls}',
                            as_of_date=date(2026,7,31),asset_class=cls,current_value=Decimal(value)))
    groups=detect_general_peer_clusters(inv,holds)
    assert any(g['member_count']==6 and 'GOLD' in g['rule_id'] for g in groups)


def test_llama_cpp_brief_accepts_sourced_placeholder_but_rejects_bare_digit(client,monkeypatch):
    from app.api import local_ai
    seed_test_group()
    token=sign_in(client)['csrf_token']
    headers={'Origin':'http://localhost:5173','X-CSRF-Token':token}
    evidence=client.get('/api/v1/investors/PAT-0/analysis').json()['allocation']['source_row_ids']
    def good(_system, facts, **kwargs):
        return {'summary':'Recorded deposit weight [[FD_PCT]] percent. Please verify the source and mandate.',
                'review_questions':['What liquidity requirements are approved?'],
                'cited_fact_ids':[evidence[0]]}
    monkeypatch.setattr(local_ai,'local_llm_json',good)
    response=client.post('/api/v1/ai/briefs',headers=headers,json={'investor_id':'PAT-0'})
    assert response.status_code==201,response.text
    assert '55.00 percent' in response.json()['summary']
    def hallucination(_system,facts, **kwargs):
        return {'summary':'The portfolio returned 98 percent, so change it immediately.',
                'review_questions':['What happened in 2025?'],
                'cited_fact_ids':[evidence[0]]}
    monkeypatch.setattr(local_ai,'local_llm_json',hallucination)
    response=client.post('/api/v1/ai/briefs',headers=headers,json={'investor_id':'PAT-0'})
    assert response.status_code==422
