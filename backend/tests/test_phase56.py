"""Phase 5/6 integration: real case lifecycle, approvals and evidence-based follow-up."""
from datetime import date, timedelta
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models import AttentionCase, AdviceRecord, FollowUpTask, AuditEvent
from tests.conftest import sign_in
from tests.test_phase34 import seed_test_group

ORIGIN={'Origin':'http://localhost:5173'}


def h(csrf):return {'X-CSRF-Token':csrf, **ORIGIN}


def create_cases(client):
    seed_test_group()
    s=sign_in(client,'supervisor@advicue.local')['csrf_token']
    resp=client.post('/api/v1/patterns/run',headers=h(s))
    assert resp.status_code==200,resp.text
    return s,resp.json()


def test_scan_creates_scoped_cases_and_is_idempotent(client):
    sup,first=create_cases(client)
    cases=client.get('/api/v1/attention').json()['items']
    assert len(cases)==5
    assert {c['priority'] for c in cases}=={'P2'}
    assert all(c['status']=='OPEN' and len(c['evidence_source_row_ids'])==4 for c in cases)
    assert all('not a suitability' in c['data_note'].lower() for c in cases)
    repeat=client.post('/api/v1/patterns/run',headers=h(sup))
    assert repeat.status_code==200,repeat.text
    assert repeat.json()['pattern_id']!=first['pattern_id']
    cases2=client.get('/api/v1/attention').json()['items']
    assert {x['id'] for x in cases2}=={x['id'] for x in cases}
    assert {x['pattern_id'] for x in cases2}=={repeat.json()['pattern_id']}
    sign_in(client)
    advisor=client.get('/api/v1/attention').json()['items']
    assert {x['investor_id'] for x in advisor}=={'PAT-0','PAT-2','PAT-4'}
    foreign=next(x['id'] for x in cases if x['investor_id']=='PAT-1')
    assert client.get('/api/v1/attention/'+foreign).status_code==404
    csrf=sign_in(client,'supervisor-c@advicue.local')['csrf_token']
    assert client.get('/api/v1/attention').json()['items']==[]
    assert client.get('/api/v1/attention/'+cases[0]['id']).status_code==404
    assert client.post('/api/v1/attention/'+cases[0]['id']+'/actions',json={'action':'START_REVIEW'},headers=h(csrf)).status_code==404


def test_case_actions_and_rescan_preserves_resolution(client):
    sup,_=create_cases(client)
    cases=client.get('/api/v1/attention').json()['items']
    case_id=next(x['id'] for x in cases if x['investor_id']=='PAT-0')
    advisor=sign_in(client)['csrf_token']
    assert client.post(f'/api/v1/attention/{case_id}/actions',json={'action':'START_REVIEW'},headers=ORIGIN).status_code==403
    start=client.post(f'/api/v1/attention/{case_id}/actions',json={'action':'START_REVIEW'},headers=h(advisor))
    assert start.status_code==200 and start.json()['status']=='IN_REVIEW'
    missing=client.post(f'/api/v1/attention/{case_id}/actions',json={'action':'REQUEST_DATA','note':'Needs mandate confirmation from investor'},headers=h(advisor))
    assert missing.status_code==200 and missing.json()['status']=='NEEDS_DATA'
    assert client.post(f'/api/v1/attention/{case_id}/actions',json={'action':'RESOLVE','note':'short'},headers=h(advisor)).status_code==422
    resolved=client.post(f'/api/v1/attention/{case_id}/actions',json={'action':'RESOLVE','note':'Reviewed source allocation; investor mandate remains to be confirmed before any change.'},headers=h(advisor))
    assert resolved.status_code==200 and resolved.json()['status']=='RESOLVED'
    # A rescan of the same holdings snapshot may refresh evidence, but must not undo the advisor's decision.
    sup=sign_in(client,'supervisor@advicue.local')['csrf_token']
    assert client.post('/api/v1/patterns/run',headers=h(sup)).status_code==200
    assert client.get('/api/v1/attention/'+case_id).json()['status']=='RESOLVED'
    advisor=sign_in(client)['csrf_token']
    assert client.post(f'/api/v1/attention/{case_id}/actions',json={'action':'START_REVIEW'},headers=h(advisor)).status_code==409
    assert client.post(f'/api/v1/attention/{case_id}/actions',json={'action':'REOPEN','note':'New relevant information requires another review'},headers=h(advisor)).json()['status']=='OPEN'


def test_advice_approval_and_follow_up_evidence(client):
    sup,_=create_cases(client)
    all_cases=client.get('/api/v1/attention').json()['items']
    a_id=next(x['id'] for x in all_cases if x['investor_id']=='PAT-0')
    b_id=next(x['id'] for x in all_cases if x['investor_id']=='PAT-1')
    adv=sign_in(client)['csrf_token']
    payload={'alert_id':a_id,'recommendation':'Contact the investor to confirm the approved mandate and investment horizon.',
             'rationale':'The dated holdings show no equity and a large deposit allocation; this calls for a review, not a trading order.',
             'assumptions':'No approved mandate is present in the supplied data.'}
    assert client.post('/api/v1/advice',json=payload,headers=ORIGIN).status_code==403
    assert client.post('/api/v1/advice',json={**payload,'alert_id':b_id},headers=h(adv)).status_code==404
    created=client.post('/api/v1/advice',json=payload,headers=h(adv))
    assert created.status_code==201,created.text
    record=created.json()
    assert record['status']=='DRAFT' and len(record['evidence_source_row_ids'])==4
    id=record['id']
    assert client.post('/api/v1/tasks',json={'advice_id':id,'title':'Review mandate','due_date':str(date.today()+timedelta(days=2))},headers=h(adv)).status_code==409
    assert client.post(f'/api/v1/advice/{id}/approve',json={'note':'Financial evidence has been reviewed.'},headers=h(adv)).status_code==403
    submit=client.post(f'/api/v1/advice/{id}/submit',headers=h(adv))
    assert submit.status_code==200 and submit.json()['status']=='SUBMITTED'
    edit=client.post(f'/api/v1/advice/{id}/edit',json={'recommendation':payload['recommendation'], 'rationale':payload['rationale']},headers=h(adv))
    assert edit.status_code==409
    sup=sign_in(client,'supervisor@advicue.local')['csrf_token']
    approval=client.post(f'/api/v1/advice/{id}/approve',json={'note':'Review recommendation only; no investment execution authorized.'},headers=h(sup))
    assert approval.status_code==200,approval.text
    assert approval.json()['status']=='APPROVED'
    assert client.post(f'/api/v1/advice/{id}/approve',json={'note':'Attempt to reapprove again.'},headers=h(sup)).status_code==409
    adv=sign_in(client)['csrf_token']
    due=(date.today()+timedelta(days=4)).isoformat()
    task=client.post('/api/v1/tasks',json={'advice_id':id,'title':'Call client to confirm the mandate','due_date':due},headers=h(adv))
    assert task.status_code==201,task.text
    task_id=task.json()['id']
    assert task.json()['status']=='OPEN'
    assert client.post(f'/api/v1/tasks/{task_id}/status',json={'status':'DONE','note':'Completed client check and documented notes.'},headers=h(adv)).status_code==422
    assert client.post(f'/api/v1/tasks/{task_id}/status',json={'status':'DONE','note':'Completed and referenced source but no reference supplied.','evidence_type':'SOURCE_REFERENCE'},headers=h(adv)).status_code==422
    done=client.post(f'/api/v1/tasks/{task_id}/status',json={'status':'DONE','note':'Advisor attests a client call was completed; this does not imply portfolio rebalancing.','evidence_type':'ADVISOR_ATTESTATION'},headers=h(adv))
    assert done.status_code==200,done.text
    assert done.json()['status']=='DONE' and done.json()['evidence_type']=='ADVISOR_ATTESTATION'
    assert client.post(f'/api/v1/tasks/{task_id}/status',json={'status':'IN_PROGRESS'},headers=h(adv)).status_code==409
    with SessionLocal() as db:
        assert db.get(AdviceRecord,id).status=='APPROVED'
        assert db.get(FollowUpTask,task_id).status=='DONE'
        actions=[x.action for x in db.scalars(select(AuditEvent)).all()]
        assert {'ADVICE_DRAFT_CREATED','ADVICE_SUBMITTED','ADVICE_APPROVED','FOLLOW_UP_CREATED','FOLLOW_UP_DONE'}.issubset(actions)


def test_supervisor_approval_other_tenant_and_task_scoping(client):
    sup,_=create_cases(client)
    a_id=next(x['id'] for x in client.get('/api/v1/attention').json()['items'] if x['investor_id']=='PAT-0')
    advisor=sign_in(client)['csrf_token']
    r=client.post('/api/v1/advice',json={'alert_id':a_id,'recommendation':'Arrange mandate review with assigned client.', 'rationale':'Recorded position requires mandate confirmation before decisions.'},headers=h(advisor))
    assert r.status_code==201,r.text
    record_id=r.json()['id']
    assert client.post('/api/v1/advice/'+record_id+'/submit',headers=h(advisor)).status_code==200
    other=sign_in(client,'supervisor-c@advicue.local')['csrf_token']
    assert client.get('/api/v1/advice/'+record_id).status_code==404
    assert client.post(f'/api/v1/advice/{record_id}/approve',json={'note':'Not authorized to see this client.'},headers=h(other)).status_code==404
    sup=sign_in(client,'supervisor@advicue.local')['csrf_token']
    assert client.post('/api/v1/advice/'+record_id+'/reject',json={'note':'Need supporting client mandate details.'},headers=h(sup)).status_code==200
    advisor=sign_in(client)['csrf_token']
    assert client.post('/api/v1/tasks',json={'advice_id':record_id,'title':'Schedule mandate review','due_date':str(date.today()+timedelta(days=1))},headers=h(advisor)).status_code==409
    retry=client.post('/api/v1/advice',json={'alert_id':a_id,'recommendation':'Contact client for confirmation of the risk mandate.', 'rationale':'Prior proposal lacked enough evidence and was rejected.','supersedes_id':record_id},headers=h(advisor))
    assert retry.status_code==201 and retry.json()['supersedes_id']==record_id


def test_imported_advisor_activation_preserves_assigned_investors(client, monkeypatch):
    """Local demo admin workflow: activated advisor sees only its imported source-code clients."""
    from tests.test_phase2 import DATA_FILE, upload
    import sys
    from app.scripts.activate_imported_advisor import main
    from app.models import User, Investor
    from sqlalchemy import select
    if not DATA_FILE.exists():
        import pytest
        pytest.skip('Original sample workbook is not bundled with the source')
    su=sign_in(client,'supervisor@advicue.local')['csrf_token']
    r=upload(client,su,DATA_FILE.read_bytes(),DATA_FILE.name)
    assert r.status_code==201,r.text
    r2=client.post(f"/api/v1/imports/{r.json()['id']}/commit",headers=h(su))
    assert r2.status_code==200,r2.text
    with SessionLocal() as db:
        placeholder=db.scalar(select(User).where(User.external_advisor_code=='ADV06'))
        before_id=placeholder.id
        assert not placeholder.is_active
        before_ids={r.id for r in db.scalars(select(Investor).where(Investor.advisor_id==before_id)).all()}
        assert {'INV0009','INV0013'}.issubset(before_ids)
    monkeypatch.setattr(sys,'argv',['activate_imported_advisor','--organization-id','org-a','--code','ADV06','--email','demo-adv06@advicue.local',
        '--name','Sample Advisor 06','--password','LocalPasswordExample123!'])
    main()
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.external_advisor_code=='ADV06'))
        assert user.is_active and user.id==before_id
        after_ids={r.id for r in db.scalars(select(Investor).where(Investor.advisor_id==user.id)).all()}
        assert after_ids==before_ids
    login=client.post('/api/v1/auth/login',json={'email':'demo-adv06@advicue.local','password':'LocalPasswordExample123!'},headers=ORIGIN)
    assert login.status_code==200, login.text
    vis={r['id'] for r in client.get('/api/v1/investors').json()['items']}
    assert vis==before_ids
