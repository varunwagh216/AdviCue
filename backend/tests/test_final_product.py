"""Final product: separate admin controls, advisor self-finalization and strict tenant isolation."""
from datetime import date, timedelta
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models import AdviceRecord, Organization, AuditEvent
from tests.conftest import sign_in
from tests.test_phase56 import create_cases, h


def make_advice(client):
    create_cases(client)
    sign=sign_in(client)['csrf_token']
    cases=client.get('/api/v1/attention').json()['items']
    case=next(x for x in cases if x['investor_id']=='PAT-0')
    resp=client.post('/api/v1/advice',headers=h(sign),json={
        'alert_id':case['id'],
        'recommendation':'Contact the client to verify the recorded investment mandate.',
        'rationale':'Observed allocation may warrant a review but is not proof of unsuitable advice.'})
    assert resp.status_code==201,resp.text
    return resp.json()['id'],sign


def test_admin_overview_is_private_and_policy_is_audited(client):
    assert client.get('/api/v1/admin/overview').status_code==401
    advisor=sign_in(client)['csrf_token']
    assert client.get('/api/v1/admin/overview').status_code==403
    assert client.post('/api/v1/admin/policy',headers=h(advisor),json={'approval_required':True}).status_code==403
    admin=sign_in(client,'supervisor@advicue.local')['csrf_token']
    info=client.get('/api/v1/admin/overview')
    assert info.status_code==200
    assert info.json()['investor_count']==2
    assert info.json()['approval_required'] is False
    assert client.post('/api/v1/admin/policy',json={'approval_required':True},headers={'Origin':'http://localhost:5173'}).status_code==403
    result=client.post('/api/v1/admin/policy',headers=h(admin),json={'approval_required':True})
    assert result.status_code==200 and result.json()['approval_required'] is True
    assert client.get('/api/v1/workflow-policy').json()['approval_required'] is True
    with SessionLocal() as db:
        assert db.get(Organization,'org-a').approval_required is True
        assert 'APPROVAL_POLICY_UPDATED' in [a.action for a in db.scalars(select(AuditEvent)).all()]
    sign_in(client,'supervisor-c@advicue.local')
    assert client.get('/api/v1/workflow-policy').json()['approval_required'] is False


def test_advisor_finalizes_without_extra_admin_approval(client):
    rid,token=make_advice(client)
    done=client.post(f'/api/v1/advice/{rid}/finalize',headers=h(token),json={
        'note':'Advisor verifies this is a request for client mandate review, not a trade.'})
    assert done.status_code==200,done.text
    assert done.json()['status']=='APPROVED'
    assert done.json()['decided_by']=='advisor-a'
    assert client.post(f'/api/v1/advice/{rid}/finalize',headers=h(token),json={
        'note':'Try finalizing the same record twice.'}).status_code==409
    assert client.post(f'/api/v1/advice/{rid}/edit',headers=h(token),json={
        'recommendation':'Try to change approved advice.',
        'rationale':'Approved advice must never be silently overwritten.'}).status_code==409
    task=client.post('/api/v1/tasks',headers=h(token),json={
        'advice_id':rid,'title':'Schedule client allocation review',
        'due_date':(date.today()+timedelta(days=2)).isoformat()})
    assert task.status_code==201,task.text
    with SessionLocal() as db:
        assert 'ADVICE_ADVISOR_FINALIZED' in [a.action for a in db.scalars(select(AuditEvent)).all()]


def test_admin_policy_blocks_advisor_finalization_and_scope(client):
    rid,token=make_advice(client)
    admin=sign_in(client,'supervisor@advicue.local')['csrf_token']
    assert client.post('/api/v1/admin/policy',headers=h(admin),json={'approval_required':True}).status_code==200
    advisor=sign_in(client)['csrf_token']
    resp=client.post(f'/api/v1/advice/{rid}/finalize',headers=h(advisor),json={
        'note':'Advisor should not bypass the active admin-approval policy.'})
    assert resp.status_code==403
    assert client.post(f'/api/v1/advice/{rid}/submit',headers=h(advisor)).json()['status']=='SUBMITTED'
    other=sign_in(client,'supervisor-c@advicue.local')['csrf_token']
    assert client.post(f'/api/v1/advice/{rid}/approve',headers=h(other),json={
        'note':'Different tenant must not approve this advice.'}).status_code==404
    admin=sign_in(client,'supervisor@advicue.local')['csrf_token']
    assert client.post(f'/api/v1/advice/{rid}/approve',headers=h(admin),json={
        'note':'Admin confirms a review-only recommendation has enough supporting evidence.'}).status_code==200


def test_sqlite_decimal_storage_preserves_cents():
    """The demo database uses SQLite NUMERIC columns with a two-decimal schema."""
    from decimal import Decimal
    from sqlalchemy import Numeric, Column, Table, MetaData, create_engine, insert, select
    engine = create_engine('sqlite+pysqlite:///:memory:')
    table = Table('money_check', MetaData(), Column('amount', Numeric(22, 2)))
    table.metadata.create_all(engine)
    with engine.begin() as conn:
        conn.execute(insert(table).values(amount=Decimal('1234567.89')))
        value = conn.scalar(select(table.c.amount))
    assert value == Decimal('1234567.89')


def test_sqlalchemy_tables_compile_for_sqlite():
    """Check the actual judge demo dialect rather than an unused PostgreSQL dialect."""
    from sqlalchemy.schema import CreateTable
    from sqlalchemy.dialects import sqlite
    from app.core.database import Base
    import app.models  # noqa: F401
    dialect = sqlite.dialect()
    statements = [str(CreateTable(table).compile(dialect=dialect)) for table in Base.metadata.sorted_tables]
    assert any('organizations' in statement and 'approval_required' in statement for statement in statements)
    assert all('CREATE TABLE' in statement for statement in statements)
