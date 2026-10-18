"""Phase 3 financial safeguards and Phase 4 role-scoped pattern workflow."""
from datetime import date
from decimal import Decimal
from pathlib import Path
import pytest
from sqlalchemy import select
from app.engines.financial import allocation_for_holdings, goal_scenarios, linked_twr, months_remaining, recorded_value_change, xirr
from app.engines.patterns import detect_low_equity_fd
from app.models import Holding, Investor, PatternRun, DetectedPattern, PatternMember, ImportBatch, SourceRow
from app.core.database import SessionLocal
from tests.conftest import sign_in
from tests.test_phase2 import DATA_FILE, make_workbook, upload


def test_financial_math_and_scenario_assumptions():
    assert recorded_value_change(Decimal('100'),Decimal('125')) == '25.00'
    assert recorded_value_change(Decimal('0'),Decimal('125')) is None
    assert linked_twr([Decimal('.1'),Decimal('-.1')]) == Decimal('-.01')
    assert abs(xirr([(date(2025,1,1),Decimal('-1000')),(date(2026,1,1),Decimal('1100'))])-Decimal('.1')) < Decimal('.00001')
    with pytest.raises(ValueError): xirr([(date(2025,1,1),Decimal('-1000')),(date(2026,1,1),Decimal('-200'))])
    scenarios=goal_scenarios(principal=Decimal('500000'),monthly_contribution=Decimal('10000'),
        target_amount=Decimal('1200000'),months=60,annual_rates=[Decimal('0'),Decimal('.08')])
    assert scenarios[0]['projected_value']=='1100000.00'
    assert Decimal(scenarios[1]['projected_value']) > Decimal('1100000')
    assert months_remaining(date(2026,7,31),date(2027,7,31))==12
    with pytest.raises(ValueError):goal_scenarios(principal=Decimal('-1'),monthly_contribution=Decimal(0),target_amount=Decimal(1),months=12,annual_rates=[Decimal('.08')])


def test_same_date_allocation_and_no_holdings():
    class Hold:
        def __init__(self,asset_class,value,when,row):
            self.asset_class=asset_class;self.current_value=Decimal(value);self.as_of_date=date.fromisoformat(when);self.source_row_id=row
    a=allocation_for_holdings([Hold('Fixed Deposit','500','2026-07-31','row1'),
        Hold('Direct Equity','500','2026-07-31','row2'),Hold('Fixed Deposit','999999','2025-07-31','row3')])
    assert a['total_value']=='1000.00' and a['equity_pct']=='50.00' and a['fixed_deposit_pct']=='50.00'
    assert set(a['source_row_ids'])=={'row1','row2'}
    assert allocation_for_holdings([])['status']=='NO_HOLDINGS'


def test_import_financial_analysis_and_goals(client):
    su=sign_in(client,'supervisor@advicue.local')
    r=upload(client,su['csrf_token'],make_workbook());assert r.status_code==201,r.text
    saved=client.post(f"/api/v1/imports/{r.json()['id']}/commit",headers={'X-CSRF-Token':su['csrf_token'],'Origin':'http://localhost:5173'})
    assert saved.status_code==200,saved.text
    resp=client.get('/api/v1/investors/DEMO-001/analysis');assert resp.status_code==200,resp.text
    body=resp.json()
    assert body['allocation']['total_value']=='11000.00'
    assert body['allocation']['fixed_deposit_pct']=='100.00'
    assert body['allocation']['as_of_date']=='2026-07-31'
    assert body['performance']['status']=='NOT_ASSESSABLE'
    assert body['performance']['benchmark_status']=='NO_APPROVED_BENCHMARK'
    wrong=client.post('/api/v1/investors/DEMO-001/goal-scenarios',json={'principal':'5000','monthly_contribution':'250','as_of_date':'2026-07-31'},headers={'Origin':'http://localhost:5173'})
    assert wrong.status_code==403  # CSRF
    good=client.post('/api/v1/investors/DEMO-001/goal-scenarios',json={
        'principal':'5000','monthly_contribution':'250','as_of_date':'2026-07-31',
        'annual_return_assumptions_pct':['4','8','12']},headers={'X-CSRF-Token':su['csrf_token'],'Origin':'http://localhost:5173'})
    assert good.status_code==200,good.text
    assert len(good.json()['scenarios'])==3
    assert 'Illustrative' in good.json()['disclaimer']
    assert client.get('/api/v1/investors/A-001/analysis').status_code==200
    assert client.get('/api/v1/investors/B-001/analysis').status_code==404
    assert client.get('/api/v1/investors/B-001/analysis').json()['detail']=='Investor not found'
    # Advisor A must not read a client imported under unlinked advisor code.
    sign_in(client)
    assert client.get('/api/v1/investors/DEMO-001/analysis').status_code==404
    assert client.get('/api/v1/investors/B-001/analysis').status_code==404


def seed_test_group(org='org-a',advisor_ids=('advisor-a','advisor-b')):
    with SessionLocal() as db:
        batch=ImportBatch(organization_id=org,uploaded_by="supervisor-a",filename="test-group.xlsx",file_sha256="a"*64,status="COMMITTED",total_rows=20,error_count=0,warning_count=0,sheet_counts={})
        db.add(batch);db.flush()
        for k in range(5):
            investor=f'PAT-{k}'
            advisor=advisor_ids[k%len(advisor_ids)]
            db.add(Investor(id=investor,organization_id=org,advisor_id=advisor,display_name=investor,
                            risk_profile='Moderate',source_advisor_code=f'ADV{k%len(advisor_ids)+1:02d}'))
            db.flush()
            for j,(cls,val) in enumerate([('Fixed Deposit','550'),('Debt Mutual Fund','250'),('Cash/Liquid Fund','100'),('Gold ETF','100')]):
                source=SourceRow(batch_id=batch.id,sheet_name='holdings',row_number=k*4+j+2,raw_data={},normalized_data={},accepted=True)
                db.add(source);db.flush()
                db.add(Holding(organization_id=org,investor_id=investor,source_row_id=source.id,
                               external_holding_id=f'H{k}{j}',as_of_date=date(2026,7,31),asset_class=cls,
                               instrument_name=cls,current_value=Decimal(val)))
        db.commit()


def test_patterns_detection_role_scoping_and_audit(client):
    seed_test_group()
    su=sign_in(client,'supervisor@advicue.local')
    assert client.get('/api/v1/patterns').json()['items']==[]
    assert client.post('/api/v1/patterns/run').status_code==403
    r=client.post('/api/v1/patterns/run',headers={'X-CSRF-Token':su['csrf_token'],'Origin':'http://localhost:5173'})
    assert r.status_code==200,r.text
    assert r.json()['matched'] and r.json()['member_count']==5 and r.json()['advisor_count']==2
    ls=client.get('/api/v1/patterns');p=ls.json()['items'][0]
    assert p['member_count']==5 and len(p['members'])==5 and p['recorded_value_total']=='5000.00'
    sign_in(client)
    scoped=client.get('/api/v1/patterns').json()['items'][0]
    assert scoped['member_count']==5 and scoped['advisor_count']==2 and scoped['assigned_member_count']==3
    assert scoped['recorded_value_total']=='5000.00'  # non-identifying group aggregate
    assert {m['investor_id'] for m in scoped['members']}=={'PAT-0','PAT-2','PAT-4'}
    assert client.post('/api/v1/patterns/run',headers={'X-CSRF-Token':su['csrf_token'],'Origin':'http://localhost:5173'}).status_code==403
    sign_in(client,'supervisor-c@advicue.local')
    assert client.get('/api/v1/patterns').json()['items']==[]
    assert client.get(f"/api/v1/patterns/{p['id']}").status_code==404
    with SessionLocal() as db:
        assert len(db.scalars(select(PatternRun)).all())==1
        assert len(db.scalars(select(DetectedPattern)).all())==1
        assert len(db.scalars(select(PatternMember)).all())==5


@pytest.mark.skipif(not DATA_FILE.exists(), reason='Original workbook not bundled with public source')
def test_actual_dataset_eight_investors_six_advisors(client):
    su=sign_in(client,'supervisor@advicue.local')
    r=upload(client,su['csrf_token'],DATA_FILE.read_bytes())
    assert r.status_code==201,r.text
    assert r.json()['sheet_counts']=={'investors':48,'holdings':208,'transactions':394,'performance_history':576}
    committed=client.post(f"/api/v1/imports/{r.json()['id']}/commit",headers={'X-CSRF-Token':su['csrf_token'],'Origin':'http://localhost:5173'})
    assert committed.status_code==200,committed.text
    result=client.post('/api/v1/patterns/run',headers={'X-CSRF-Token':su['csrf_token'],'Origin':'http://localhost:5173'})
    assert result.status_code==200,result.text
    found=result.json()
    assert found['matched'] and found['member_count']==8 and found['advisor_count']==6
    assert found['as_of_date']=='2026-07-31'
    rows=client.get('/api/v1/patterns').json()['items'][0]['members']
    assert [m['investor_id'] for m in rows]==[f'INV{i:04d}' for i in range(9,17)]
    assert Decimal(found['recorded_value_total'])==Decimal('5277585.72')
    analysis=client.get('/api/v1/investors/INV0009/analysis').json()
    assert analysis['allocation']['equity_pct']=='0.00'
    assert analysis['performance']['status']=='NOT_ASSESSABLE'
