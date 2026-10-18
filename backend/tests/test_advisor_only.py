"""Advisor-only judge demo: preserve all scoping and write-permission boundaries."""
from types import SimpleNamespace
from sqlalchemy import select
from app.core import access
from app.core.database import SessionLocal
from app.models import AuditEvent
from tests.conftest import sign_in
from tests.test_phase2 import make_workbook, upload
from tests.test_phase34 import seed_test_group


def demo_permissions(monkeypatch, *, enabled=True, app_env='demo', email='advisor@advicue.local'):
    monkeypatch.setattr(access, 'settings', SimpleNamespace(
        app_env=app_env,
        advisor_demo_operations_enabled=enabled,
        advisor_demo_operator_email=email,
    ))


def headers(token):
    return {'Origin':'http://localhost:5173', 'X-CSRF-Token':token}


def test_advisor_demo_operator_can_validate_commit_and_see_only_own_clients(client, monkeypatch):
    demo_permissions(monkeypatch)
    token=sign_in(client)['csrf_token']
    caps=client.get('/api/v1/advisor-capabilities')
    assert caps.status_code==200 and caps.json()['can_manage_workbooks']
    assert caps.json()['can_run_group_scan']
    result=upload(client,token,make_workbook())
    assert result.status_code==201,result.text
    batch_id=result.json()['id']
    assert client.get('/api/v1/imports').status_code==200
    assert client.get(f'/api/v1/imports/{batch_id}/issues').status_code==200
    result=client.post(f'/api/v1/imports/{batch_id}/commit',headers=headers(token))
    assert result.status_code==200,result.text
    own={i['id'] for i in client.get('/api/v1/investors').json()['items']}
    assert own == {'A-001'}  # demo importer must not acquire clients in other books
    assert client.get('/api/v1/investors/DEMO-001').status_code==404
    with SessionLocal() as db:
        assert db.scalar(select(AuditEvent).where(AuditEvent.action=='IMPORT_COMMITTED')) is not None


def test_advisor_demo_operator_can_scan_and_get_private_details_only(client, monkeypatch):
    demo_permissions(monkeypatch)
    seed_test_group()
    token=sign_in(client)['csrf_token']
    scan=client.post('/api/v1/patterns/run',headers=headers(token))
    assert scan.status_code==200,scan.text
    assert scan.json()['member_count']==5 and scan.json()['advisor_count']==2
    group=client.get('/api/v1/patterns').json()['items'][0]
    assert group['member_count']==5 and group['advisor_count']==2
    assert group['assigned_member_count']==3
    assert group['recorded_value_total']=='5000.00'
    assert {m['investor_id'] for m in group['members']}=={'PAT-0','PAT-2','PAT-4'}
    assert client.get('/api/v1/investors/PAT-1').status_code==404
    assert client.get('/api/v1/investors/PAT-1/analysis').status_code==404
    assert client.get('/api/v1/attention').json()['total_visible']==3
    other_token=sign_in(client,'b@advicue.local')['csrf_token']
    assert client.get('/api/v1/advisor-capabilities').json()['can_run_group_scan'] is False
    assert client.post('/api/v1/patterns/run',headers=headers(other_token)).status_code==403
    assert client.get('/api/v1/patterns').json()['items'][0]['assigned_member_count']==2
    assert client.get('/api/v1/investors/PAT-0').status_code==404
    assert client.post('/api/v1/imports',files={'file':('test.xlsx',make_workbook())},headers=headers(other_token)).status_code==403


def test_demo_operator_permission_defaults_to_off(client, monkeypatch):
    demo_permissions(monkeypatch,enabled=False)
    token=sign_in(client)['csrf_token']
    assert client.get('/api/v1/advisor-capabilities').json()['can_manage_workbooks'] is False
    assert client.post('/api/v1/patterns/run',headers=headers(token)).status_code==403
    assert upload(client,token,make_workbook()).status_code==403


def test_demo_operator_disabled_in_production_even_if_flag_enabled(client, monkeypatch):
    demo_permissions(monkeypatch,enabled=True,app_env='production')
    token=sign_in(client)['csrf_token']
    assert client.get('/api/v1/advisor-capabilities').json()['can_manage_workbooks'] is False
    assert client.post('/api/v1/patterns/run',headers=headers(token)).status_code==403
    assert upload(client,token,make_workbook()).status_code==403


def test_demo_operator_requires_exact_login_email(client, monkeypatch):
    demo_permissions(monkeypatch,email='somebody-else@advicue.local')
    token=sign_in(client)['csrf_token']
    assert client.get('/api/v1/advisor-capabilities').json()['can_manage_workbooks'] is False
    assert client.post('/api/v1/patterns/run',headers=headers(token)).status_code==403
