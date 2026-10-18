"""Phase 9 acceptance: scoped read-only readiness and a complete advice loop."""
from datetime import date, timedelta
from sqlalchemy import select, func
from app.core.database import SessionLocal
from app.models import AuditEvent
from tests.conftest import sign_in
from tests.test_phase56 import create_cases, h


def test_readiness_needs_login_and_does_not_expose_private_imports(client):
    assert client.get('/api/v1/demo/readiness').status_code == 401
    sign_in(client)
    r = client.get('/api/v1/demo/readiness')
    assert r.status_code == 200, r.text
    x = r.json()
    assert x['phase'] == 9
    assert x['role'] == 'ADVISOR'
    assert x['overview']['committed_import_count'] is None
    assert x['overview']['investor_count'] == 1
    assert x['workflow_evidence_ready'] is False
    assert x['total_checks'] == 8
    assert x['optional_ai']['status'] == 'RECORDED_EVIDENCE_ONLY'
    assert 'NOT_ASSESSABLE' in x['finance_safeguards']['portfolio_return']
    assert 'production certification' in x['note']
    assert client.get('/api/v1/demo/readiness').headers['cache-control'] == 'no-store'


def test_readiness_is_read_only(client):
    sign_in(client, 'supervisor@advicue.local')
    with SessionLocal() as db:
        before = db.scalar(select(func.count()).select_from(AuditEvent))
    first = client.get('/api/v1/demo/readiness')
    second = client.get('/api/v1/demo/readiness')
    assert first.status_code == second.status_code == 200
    with SessionLocal() as db:
        after = db.scalar(select(func.count()).select_from(AuditEvent))
    assert before == after


def test_role_scoped_release_status_does_not_leak_other_org_or_advisor(client):
    create_cases(client)
    supervisor = client.get('/api/v1/demo/readiness').json()
    assert supervisor['overview']['attention_case_count'] == 5
    sign_in(client)
    advisor = client.get('/api/v1/demo/readiness').json()
    assert advisor['overview']['attention_case_count'] == 3
    assert advisor['overview']['committed_import_count'] is None
    sign_in(client, 'supervisor-c@advicue.local')
    outsider = client.get('/api/v1/demo/readiness').json()
    assert outsider['overview']['attention_case_count'] == 0
    assert outsider['overview']['pattern_count'] == 0
    assert outsider['overview']['approved_advice_count'] == 0


def test_complete_detect_review_approve_follow_up_and_audit(client):
    _, _ = create_cases(client)
    supervisor = client.get('/api/v1/demo/readiness').json()
    assert supervisor['overview']['pattern_count'] > 0
    assert supervisor['overview']['attention_case_count'] == 5
    assert supervisor['workflow_evidence_ready'] is False

    sign = sign_in(client)['csrf_token']
    cases = client.get('/api/v1/attention').json()['items']
    case = next(x for x in cases if x['investor_id'] == 'PAT-0')
    start = client.post(f"/api/v1/attention/{case['id']}/actions", headers=h(sign),
                        json={'action':'START_REVIEW'})
    assert start.status_code == 200, start.text
    created = client.post('/api/v1/advice', headers=h(sign), json={
        'alert_id':case['id'],
        'recommendation':'Ask the investor to confirm the intended target allocation and liquidity horizon.',
        'rationale':'Imported dated holdings indicate an allocation worth reviewing, not a suitability finding.'})
    assert created.status_code == 201, created.text
    advice_id = created.json()['id']
    assert client.post(f'/api/v1/advice/{advice_id}/submit', headers=h(sign)).status_code == 200
    supervisor_token = sign_in(client, 'supervisor@advicue.local')['csrf_token']
    approved = client.post(f'/api/v1/advice/{advice_id}/approve', headers=h(supervisor_token), json={
        'note':'Approval is limited to an information-gathering review, not a trade.'})
    assert approved.status_code == 200, approved.text
    advisor_token = sign_in(client)['csrf_token']
    task = client.post('/api/v1/tasks', headers=h(advisor_token), json={
        'advice_id':advice_id,
        'title':'Contact the investor about mandate confirmation',
        'due_date':str(date.today() + timedelta(days=3))})
    assert task.status_code == 201, task.text
    done = client.post(f"/api/v1/tasks/{task.json()['id']}/status", headers=h(advisor_token), json={
        'status':'DONE', 'evidence_type':'ADVISOR_ATTESTATION',
        'note':'ILLUSTRATIVE DEMO: Advisor attests a follow-up call took place; no investment was executed.'})
    assert done.status_code == 200, done.text
    ready = client.get('/api/v1/demo/readiness').json()
    assert ready['overview']['approved_advice_count'] >= 1
    assert ready['overview']['verified_task_count'] >= 1
    assert ready['workflow_evidence_ready'] is True
    assert all(x['ready'] for x in ready['checks'])
    # The demo does not infer that the advisor did anything beyond an attested task.
    assert ready['finance_safeguards']['allocation_pattern'].startswith('REVIEW SIGNAL')


def test_optional_ai_cannot_block_deterministic_release_checks(client):
    create_cases(client)
    r = client.get('/api/v1/demo/readiness')
    assert r.status_code == 200
    assert r.json()['optional_ai']['briefs_created'] == 0
    assert r.json()['overview']['attention_case_count'] > 0
