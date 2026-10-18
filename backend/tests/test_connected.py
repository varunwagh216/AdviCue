from copy import deepcopy
from datetime import date,datetime,timedelta,timezone
from types import SimpleNamespace as NS
from unittest.mock import patch
from decimal import Decimal as D
import csv,io
import pytest
from sqlalchemy import select,func
from app.core.database import SessionLocal
from app.models import Investor,User,AttentionCase,AdviceRecord,ReviewEvidence,FollowUpTask,PilotSession,Holding
from app.services.monitoring import refresh_clients,client_signals
from app.engines.advice_evidence import objective_review
from app.ai.local_models import LocalModelError
from tests.conftest import sign_in
from tests.test_evidence import sample


def headers(client):return {'Origin':'http://localhost:5173','X-CSRF-Token':sign_in(client)['csrf_token']}


def objective_fixture():
    p=sample();p['periods'][0]['start_date']='2026-01-02'
    a=NS(id='advice',investor_id='A-001',status='APPROVED',decided_at=datetime(2026,1,1,tzinfo=timezone.utc),expected_outcome='Beat reviewed benchmark by at least one percentage point.',outcome_rule={'metric':'active_return_pp','comparator':'>=','target_pct':1,'due_date':'2026-02-02','window_start':'2026-01-02','window_end':'2026-02-01'})
    e=NS(id='evidence',kind='PERFORMANCE',status='APPROVED',payload=p,payload_sha256='a'*64,approved_at=datetime(2026,2,3,tzinfo=timezone.utc))
    return a,e


def test_objective_uses_approved_exact_window_and_keeps_synthetic_label():
    a,e=objective_fixture();r=objective_review(a,[],[e],today=date(2026,3,1))
    assert r['status']=='OBJECTIVE_MET' and D(r['observed_value'])==2
    assert r['evidence_sha256']=='a'*64 and r['illustrative'] is True
    a.outcome_rule['target_pct']=3
    assert objective_review(a,[],[e],today=date(2026,3,1))['status']=='OBJECTIVE_NOT_MET'


@pytest.mark.parametrize('fault',['draft','wrong_client','boundary','approval_day','future_window'])
def test_financial_objective_refuses_unsuitable_evidence(fault):
    a,e=objective_fixture();today=date(2026,3,1)
    if fault=='draft':e.status='DRAFT'
    if fault=='wrong_client':e.payload['client_id']='A-002'
    if fault=='boundary':a.outcome_rule['window_start']='2026-01-03'
    if fault=='approval_day':a.decided_at=datetime(2026,1,2,tzinfo=timezone.utc)
    if fault=='future_window':today=date(2026,1,20)
    assert objective_review(a,[],[e],today=today)['status'] in ('EVIDENCE_REQUIRED','APPROVAL_AFTER_WINDOW','PENDING_WINDOW')


def test_window_can_select_complete_subperiods_without_counting_outside_returns():
    a,e=objective_fixture();second=deepcopy(e.payload['periods'][0]);second.update(start_date='2026-02-01',end_date='2026-03-01',start_value='107000',end_value='117700')
    for c in second['classes']:c['start_value']=c['end_value'];c['end_value']=str(D(c['start_value'])*D('1.1'))
    e.payload['periods'].append(second)
    assert D(objective_review(a,[],[e],today=date(2026,3,2))['observed_value'])==2


def test_advice_review_persists_calculation_and_is_scoped(client):
    h=headers(client)
    case=client.post('/api/v1/attention',headers=h,json={'investor_id':'A-001','title':'Check recorded objective','reason':'Client agreed a source-based outcome review.'}).json()
    a,e=objective_fixture()
    draft=client.post('/api/v1/advice',headers=h,json={'alert_id':case['id'],'recommendation':'Review the agreed financial objective.','rationale':'Use dated reviewed client evidence only.','expected_outcome':a.expected_outcome,'review_date':'2026-02-02','outcome_rule':a.outcome_rule})
    assert draft.status_code==201,draft.text
    aid=draft.json()['id']
    with patch('app.api.workflow._now',return_value=datetime(2026,1,1,tzinfo=timezone.utc)):
        assert client.post('/api/v1/advice/'+aid+'/finalize',headers=h,json={'note':'Agreed the objective before the measurement began.'}).status_code==200
    staged=client.post('/api/v1/investors/A-001/performance-evidence',headers=h,json=e.payload).json()
    assert client.get('/api/v1/advice/'+aid+'/outcome').json()['agreed_objective']['status']=='EVIDENCE_REQUIRED'
    assert client.post('/api/v1/investors/A-001/evidence/'+staged['id']+'/approve',headers=h,json={'source_review_completed':True,'note':'Reviewed synthetic flows, values and benchmark for this test.'}).status_code==200
    result=client.get('/api/v1/advice/'+aid+'/outcome').json()['agreed_objective'];assert result['status']=='OBJECTIVE_MET'
    saved=client.post('/api/v1/advice/'+aid+'/outcome-reviews',headers=h,json={'evidence_id':staged['id'],'note':'Reviewed the source-bound synthetic objective and its measurement window.'})
    assert saved.status_code==201,saved.text
    assert saved.json()['result']['evidence_sha256']==result['evidence_sha256']
    sign_in(client,'b@advicue.local')
    assert client.get('/api/v1/advice/'+aid+'/outcome').status_code==404


def test_financial_objective_cannot_be_finalized_after_window_started(client):
    h=headers(client);a,e=objective_fixture()
    case=client.post('/api/v1/attention',headers=h,json={'investor_id':'A-001','title':'Review financial window','reason':'Do not apply a retrospective financial objective.'}).json()
    draft=client.post('/api/v1/advice',headers=h,json={'alert_id':case['id'],'recommendation':'Review the recorded objective with the client.','rationale':'The evaluation period must follow approval.','outcome_rule':a.outcome_rule}).json()
    assert client.post('/api/v1/advice/'+draft['id']+'/finalize',headers=h,json={'note':'Attempted retrospective financial review approval.'}).status_code==422


def test_unchanged_monitoring_does_not_reopen_next_day_but_new_condition_does(client):
    with SessionLocal() as db:
        user=db.get(User,'advisor-a');first=refresh_clients(db,user);cid=first['items'][0]['case_id'];row=db.get(AttentionCase,cid);row.status='RESOLVED';row.resolved_at=datetime.now(timezone.utc);row.resolution_note='Known source issue documented.';db.commit()
        class Tomorrow(date):
            @classmethod
            def today(cls):return date.today()+timedelta(days=1)
        with patch('app.services.monitoring.date',Tomorrow):
            again=refresh_clients(db,user)
        assert again['cases_created']==0 and db.get(AttentionCase,cid).status=='RESOLVED'
        db.add(FollowUpTask(organization_id='org-a',investor_id='A-001',owner_id='advisor-a',title='New overdue commitment',due_date=date.today()-timedelta(days=1)));db.commit()
        changed=refresh_clients(db,user);assert changed['cases_created']==1


def test_goal_plan_does_not_need_reconfirmation_every_day():
    today=date.today();inv=NS(goal_target_date=today+timedelta(days=365),goal_target_amount=D('1000000'))
    p=NS(as_of_date=today-timedelta(days=1),principal=D('100'),monthly_contribution=D('100'),annual_rates=['4','8','12'])
    holding=NS(as_of_date=today,asset_class='Direct Equity',current_value=D(100),source_row_id='source')
    signals=client_signals(inv,[holding],[],[],p,[],None,None,today=today)
    assert {s['rule_id'] for s in signals}=={'GOAL_FUNDING_GAP'}


def csv_payload(iid='A-001',value='100000'):
    return f'client_id,holding_id,as_of_date,asset_class,instrument_name,current_value\n{iid},H1,{date.today().isoformat()},Direct Equity,Synthetic holding,{value}\n'.encode()


def test_csv_intake_is_scoped_reviewed_and_idempotent(client):
    h=headers(client)
    outside=client.post('/api/v1/connections/holdings-csv',headers=h,files={'file':('x.csv',csv_payload('A-002'),'text/csv')});assert outside.status_code==404
    staged=client.post('/api/v1/connections/holdings-csv',headers=h,files={'file':('x.csv',csv_payload(),'text/csv')});assert staged.status_code==201,staged.text
    bid=staged.json()['id']
    assert client.post('/api/v1/connections/holdings-csv/'+bid+'/commit',headers=h,json={'complete_snapshot':False}).status_code==422
    committed=client.post('/api/v1/connections/holdings-csv/'+bid+'/commit',headers=h,json={'complete_snapshot':True});assert committed.status_code==200,committed.text
    assert committed.json()['rows_added']==1
    assert client.post('/api/v1/connections/holdings-csv/'+bid+'/commit',headers=h,json={'complete_snapshot':True}).json()['already_committed'] is True
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(Holding).where(Holding.investor_id=='A-001'))==1
    conflict=client.post('/api/v1/connections/holdings-csv',headers=h,files={'file':('x.csv',csv_payload(value='200000'),'text/csv')}).json()
    assert client.post('/api/v1/connections/holdings-csv/'+conflict['id']+'/commit',headers=h,json={'complete_snapshot':True}).status_code==409


def test_task_names_and_safe_crm_calendar_exports(client):
    with SessionLocal() as db:
        db.add(FollowUpTask(id='task-a',organization_id='org-a',investor_id='A-001',owner_id='advisor-a',title='=HYPERLINK("example")',due_date=date.today()));db.add(FollowUpTask(id='task-b',organization_id='org-a',investor_id='A-002',owner_id='advisor-b',title='Other advisor private task',due_date=date.today()));db.commit()
    sign_in(client)
    assert client.get('/api/v1/tasks/task-a').json()['investor_name']=='Test Investor A'
    assert client.get('/api/v1/tasks/task-b').status_code==404
    exported=client.get('/api/v1/connections/follow-ups.csv');rows=list(csv.DictReader(io.StringIO(exported.text)))
    assert len(rows)==1 and rows[0]['title'].startswith("'=") and rows[0]['client_name']=='Test Investor A'
    ics=client.get('/api/v1/connections/follow-ups.ics').text
    assert 'Test Investor A' in ics and 'Other advisor' not in ics and 'BEGIN:VTODO' in ics


def test_home_search_is_scoped_and_fallback_is_labelled(client):
    h=headers(client)
    with patch('app.api.workspace.local_llm_json',side_effect=LocalModelError('offline')):
        home=client.get('/api/v1/home').json();assert home['assigned_clients']==1
        result=client.post('/api/v1/assistant/search',headers=h,json={'query':'Show Test Investor A'}).json()
        assert result['mode']=='RECORD_SEARCH' and result['warning'] and result['items'][0]['client_name']=='Test Investor A'
        outside=client.post('/api/v1/assistant/search',headers=h,json={'query':'Show A-002 portfolio'}).json()
        assert outside['items']==[]
    with patch('app.api.workspace.local_llm_json',return_value={'intent':'FOLLOW_UPS','client_search':''}):
        exact=client.post('/api/v1/assistant/search',headers=h,json={'query':'Show A-001 portfolio'}).json()
        assert exact['intent']=='CLIENT' and exact['items'][0]['client_name']=='Test Investor A'


def test_pilot_captures_new_discovery_and_random_control_without_fabrication(client):
    h=headers(client)
    summary=client.get('/api/v1/pilot/summary').json();assert summary['useful_new_discoveries']==0 and summary['random_control_miss_rate'] is None
    case=client.post('/api/v1/attention',headers=h,json={'investor_id':'A-001','title':'Review a new discovery','reason':'An advisor will judge this signal independently.'}).json()
    sid=client.post('/api/v1/pilot/sessions',headers=h,json={'investor_id':'A-001','case_id':case['id']}).json()['id']
    result=client.post('/api/v1/pilot/sessions/'+sid+'/finish',headers=h,json={'outcome':'RELEVANT','already_known':False,'discovery_note':'A previously unknown recorded commitment was overdue.','voluntary_return':True});assert result.status_code==200,result.text
    assert client.get('/api/v1/pilot/summary').json()['useful_new_discoveries']==1
    with SessionLocal() as db:db.get(AttentionCase,case['id']).status='RESOLVED';db.commit()
    control=client.post('/api/v1/pilot/random-control',headers=h);assert control.status_code==201,control.text
    assert client.post('/api/v1/pilot/sessions/'+control.json()['id']+'/finish',headers=h,json={'outcome':'RELEVANT','missed_issue':True,'discovery_note':'A control review identified a missed client liquidity requirement.'}).status_code==200
    result=client.get('/api/v1/pilot/summary').json();assert result['random_controls_assessed']==1 and result['random_controls_with_missed_issues']==1
    assert 'Test Investor A' in client.get('/api/v1/pilot/observations.csv').text


def test_unassessable_random_control_is_not_counted_as_a_success_or_miss(client):
    h=headers(client);started=client.post('/api/v1/pilot/random-control',headers=h)
    assert started.status_code==201
    sid=started.json()['id']
    assert client.post('/api/v1/pilot/sessions/'+sid+'/finish',headers=h,json={'outcome':'NOT_ASSESSABLE','missed_issue':False}).status_code==422
    assert client.post('/api/v1/pilot/sessions/'+sid+'/finish',headers=h,json={'outcome':'NOT_ASSESSABLE'}).status_code==200
    summary=client.get('/api/v1/pilot/summary').json();assert summary['random_controls_assessed']==0 and summary['random_control_miss_rate'] is None


def test_pilot_export_preserves_explicit_no_and_zero(client):
    h=headers(client);sid=client.post('/api/v1/pilot/random-control',headers=h).json()['id']
    assert client.post('/api/v1/pilot/sessions/'+sid+'/finish',headers=h,json={'outcome':'RELEVANT','missed_issue':False,'voluntary_return':False}).status_code==200
    rows=list(csv.DictReader(io.StringIO(client.get('/api/v1/pilot/observations.csv').text)))
    assert rows[0]['missed_issue']=='False' and rows[0]['voluntary_return']=='False'


def test_invalid_financial_window_is_rejected_before_advice_is_saved(client):
    h=headers(client);a,e=objective_fixture();a.outcome_rule['window_end']='2026-01-01'
    case=client.post('/api/v1/attention',headers=h,json={'investor_id':'A-001','title':'Check financial window','reason':'The measurement window must have correct date order.'}).json()
    response=client.post('/api/v1/advice',headers=h,json={'alert_id':case['id'],'recommendation':'Review the agreed objective with the client.','rationale':'Use approved financial evidence for the exact window.','outcome_rule':a.outcome_rule})
    assert response.status_code==422


def test_window_uses_india_approval_day_and_pilot_timestamps_keep_utc_offset(client):
    a,e=objective_fixture();a.decided_at=datetime(2026,1,1,20,tzinfo=timezone.utc)
    assert objective_review(a,[],[e],today=date(2026,3,1))['status']=='APPROVAL_AFTER_WINDOW'
    h=headers(client)
    start=client.post('/api/v1/pilot/sessions',headers=h,json={'investor_id':'A-001'})
    assert start.status_code==201 and start.json()['started_at'].endswith('+00:00')
