from datetime import date,datetime,timedelta,timezone
from copy import deepcopy
from decimal import Decimal as D
from types import SimpleNamespace as NS
import pytest
from app.engines.evidence import PerformanceEvidence,reconcile
from app.services.monitoring import client_signals
from app.models import PilotSession
from app.core.database import SessionLocal
from tests.conftest import sign_in


def sample():
    return {'client_id':'A-001','currency':'INR','illustrative':True,'flow_statement_reference':'synthetic/flows','valuation_coverage_reference':'synthetic/boundaries','flows_complete':True,'valuation_coverage_complete':True,'boundaries_include_all_flows_and_rebalances':True,'fees_taxes_consistent':True,
        'benchmark_policy':{'name':'Synthetic balanced policy','rationale':'Synthetic test benchmark explicitly agreed for this test client.','source_reference':'synthetic/policy','client_mandate_reference':'synthetic/mandate','effective_from':'2026-01-01','effective_to':'2026-12-31','suitable_for_client':True},
        'periods':[{'start_date':'2026-01-01','end_date':'2026-02-01','start_value':'100000','end_value':'107000','flows':[],
        'classes':[{'asset_class':'Direct Equity','start_value':'60000','end_value':'66000','net_flow':'0','benchmark_weight_pct':'50','benchmark_return_pct':'8','valuation_reference':'synthetic/eq-values','benchmark_reference':'synthetic/eq-benchmark'},
                   {'asset_class':'Fixed Deposit','start_value':'40000','end_value':'41000','net_flow':'0','benchmark_weight_pct':'50','benchmark_return_pct':'2','valuation_reference':'synthetic/fd-values','benchmark_reference':'synthetic/fd-benchmark'}]}]}


def test_attribution_reconciles_known_active_gap():
    result=reconcile(PerformanceEvidence.model_validate(sample()))
    assert D(result['portfolio_twr_pct'])==7
    assert D(result['benchmark_linked_pct'])==5
    assert D(result['active_return_pp'])==2
    assert sum(D(r['total_pp']) for r in result['class_contributions'])==2
    assert sum(D(r['allocation_pp']) for r in result['class_contributions'])==D('.6')
    assert sum(D(r['selection_pp']) for r in result['class_contributions'])==D('1.25')
    assert sum(D(r['interaction_pp']) for r in result['class_contributions'])==D('.15')


def test_multiperiod_effects_link_to_compounded_gap():
    payload=sample();second=deepcopy(payload['periods'][0]);second.update(start_date='2026-02-01',end_date='2026-03-01',start_value='107000',end_value='117700')
    for c in second['classes']:c['start_value']=c['end_value'];c['end_value']=str(D(c['start_value'])*D('1.1'))
    payload['periods'].append(second)
    result=reconcile(PerformanceEvidence.model_validate(payload))
    assert D(result['active_return_pp'])==D('7.45')
    assert abs(sum(D(r['total_pp']) for r in result['class_contributions'])-D('7.45'))<D('.00001')


@pytest.mark.parametrize('fault',['flow_date','class_total','weights','coverage','unattested'])
def test_invalid_evidence_cannot_unlock_returns(fault):
    payload=sample();p=payload['periods'][0]
    if fault=='flow_date':p['flows']=[{'date':'2026-01-15','kind':'CONTRIBUTION','amount':'100','source_reference':'synthetic/flow1'}]
    if fault=='class_total':p['end_value']='999999'
    if fault=='weights':p['classes'][0]['benchmark_weight_pct']='60'
    if fault=='coverage':payload['benchmark_policy']['effective_from']='2026-01-02'
    if fault=='unattested':payload['flows_complete']=False
    with pytest.raises(ValueError):reconcile(PerformanceEvidence.model_validate(payload))


def test_cash_flow_adjustment_does_not_count_contribution_as_profit():
    payload=sample();p=payload['periods'][0];p['flows']=[{'date':'2026-02-01','kind':'CONTRIBUTION','amount':'10000','source_reference':'synthetic/flow1'}]
    p['end_value']='117000';p['classes'][0]['end_value']='76000';p['classes'][0]['net_flow']='10000'
    assert D(reconcile(PerformanceEvidence.model_validate(payload))['portfolio_twr_pct'])==7


def test_evidence_requires_explicit_approval_and_scope(client):
    auth=sign_in(client);h={'Origin':'http://localhost:5173','X-CSRF-Token':auth['csrf_token']}
    assert client.get('/api/v1/investors/A-001/verified-analysis').json()['status']=='EVIDENCE_REQUIRED'
    response=client.post('/api/v1/investors/A-001/performance-evidence',headers=h,json=sample())
    assert response.status_code==201,response.text
    eid=response.json()['id']
    assert client.get('/api/v1/investors/A-001/verified-analysis').json()['status']=='EVIDENCE_REQUIRED'
    approved=client.post(f'/api/v1/investors/A-001/evidence/{eid}/approve',headers=h,json={'source_review_completed':True,'note':'Reviewed the explicitly synthetic source references for this test.'})
    assert approved.status_code==200,approved.text
    result=client.get('/api/v1/investors/A-001/verified-analysis').json()
    assert result['status']=='ILLUSTRATIVE_RECONCILED'
    assert D(result['active_return_pp'])==2
    assert client.post(f'/api/v1/investors/A-001/evidence/{eid}/approve',headers=h,json={'source_review_completed':True,'note':'Attempting to overwrite a decided evidence record.'}).status_code==409
    sign_in(client,'b@advicue.local')
    assert client.get('/api/v1/investors/A-001/evidence').status_code==404
    assert client.get('/api/v1/investors/A-001/verified-analysis').status_code==404


def test_pilot_has_no_fabricated_results_and_records_actual_session(client):
    token=sign_in(client)['csrf_token'];h={'Origin':'http://localhost:5173','X-CSRF-Token':token}
    assert client.get('/api/v1/pilot/summary').json()['median_elapsed_seconds'] is None
    start=client.post('/api/v1/pilot/sessions',headers=h,json={'investor_id':'A-001'})
    assert start.status_code==201,start.text
    sid=start.json()['id']
    with SessionLocal() as db:r=db.get(PilotSession,sid);r.started_at=datetime.now(timezone.utc)-timedelta(seconds=60);db.commit()
    assert client.post(f'/api/v1/pilot/sessions/{sid}/finish',headers=h,json={'outcome':'RELEVANT','baseline_seconds':120}).status_code==200
    result=client.get('/api/v1/pilot/summary').json()
    assert result['reviews_completed']==1
    assert 59<=result['median_elapsed_seconds']<=65
    assert result['false_positive_rate'] is None # no case was labelled
    sign_in(client,'b@advicue.local')
    assert client.get('/api/v1/pilot/summary').json()['reviews_completed']==0


def test_independent_condition_needs_no_cohort():
    today=date.today();inv=NS(goal_target_date=None,goal_target_amount=None)
    stale=NS(as_of_date=today-timedelta(days=60),asset_class='Direct Equity',current_value=D(100),source_row_id='source1')
    task=NS(status='OPEN',due_date=today-timedelta(days=1))
    result=client_signals(inv,[stale],[task],[],None,[],None,None,today=today)
    assert {s['rule_id'] for s in result}=={'STALE_VALUATION','OVERDUE_COMMITMENT'}
    fresh=NS(as_of_date=today,asset_class='Direct Equity',current_value=D(100),source_row_id='source1')
    mandate={'effective_from':(today-timedelta(days=1)).isoformat(),'effective_to':(today+timedelta(days=100)).isoformat(),'bands':[{'asset_class':'Direct Equity','min_pct':'20','max_pct':'60'}]}
    result=client_signals(inv,[fresh],[],[],None,[],mandate,None,today=today)
    assert result[0]['rule_id']=='APPROVED_TARGET_DRIFT'


@pytest.mark.parametrize('value,offset',[(0,0),(100,1)])
def test_zero_or_future_valuations_are_data_reviews_not_mandate_drift(value,offset):
    today=date.today();inv=NS(goal_target_date=None,goal_target_amount=None)
    holding=NS(as_of_date=today+timedelta(days=offset),asset_class='Direct Equity',current_value=D(value),source_row_id='source1')
    mandate={'effective_from':today.isoformat(),'effective_to':(today+timedelta(days=100)).isoformat(),'bands':[{'asset_class':'Direct Equity','min_pct':'20','max_pct':'60'}]}
    signals=client_signals(inv,[holding],[],[],None,[],mandate,None,today=today)
    assert {s['rule_id'] for s in signals}=={'STALE_VALUATION'}


def test_withdrawal_is_not_a_negative_investment_return():
    payload=sample();p=payload['periods'][0]
    p['flows']=[{'date':p['end_date'],'kind':'WITHDRAWAL','amount':'10000','source_reference':'synthetic/withdrawal'}]
    p['end_value']='97000';p['classes'][0].update(end_value='56000',net_flow='-10000')
    result=reconcile(PerformanceEvidence.model_validate(payload))
    assert D(result['portfolio_twr_pct'])==7
    assert D(result['active_return_pp'])==2


def test_client_binding_and_mandate_approval_are_enforced(client):
    token=sign_in(client)['csrf_token'];h={'Origin':'http://localhost:5173','X-CSRF-Token':token}
    payload=sample();payload['client_id']='A-002'
    assert client.post('/api/v1/investors/A-001/performance-evidence',headers=h,json=payload).status_code==422
    mandate={'client_id':'A-001','effective_from':'2026-01-01','effective_to':'2027-01-01','source_reference':'synthetic/mandate','rationale':'Synthetic client mandate for scoped source review.','illustrative':True,'bands':[{'asset_class':'Direct Equity','min_pct':'20','max_pct':'60'}]}
    staged=client.post('/api/v1/investors/A-001/mandate',headers=h,json=mandate)
    assert staged.status_code==201,staged.text
    assert client.get('/api/v1/investors/A-001/verified-analysis').json()['mandate'] is None
    assert client.post('/api/v1/investors/A-001/evidence/'+staged.json()['id']+'/approve',headers=h,json={'source_review_completed':False,'note':'This source has deliberately not been reviewed.'}).status_code==422
    assert client.post('/api/v1/investors/A-001/evidence/'+staged.json()['id']+'/approve',headers=h,json={'source_review_completed':True,'note':'Reviewed the synthetic mandate for this test only.'}).status_code==200
    result=client.get('/api/v1/investors/A-001/verified-analysis').json()
    assert result['status']=='EVIDENCE_REQUIRED'
    assert result['mandate']['payload']['illustrative'] is True
