from sqlalchemy import select
from app.models import Investor, User
from app.core.database import SessionLocal
from app.scripts.configure_demo_book import configure_demo_book
from tests.conftest import sign_in

def test_demo_expansion_refuses_non_sample_org(client):
    import pytest
    with SessionLocal() as db:
        user=db.get(User,'advisor-a');user.email='advisor@advicue.demo';db.commit()
        with pytest.raises(RuntimeError,match='original 48-investor'):
            configure_demo_book(db)
        assert db.get(Investor,'A-002').advisor_id=='advisor-b'

def test_long_tail_distinguishes_portfolio_and_verification_cases(client):
    from app.models import AttentionCase
    from datetime import date
    with SessionLocal() as db:
        for iid,priority in [('A-001','P1'),('A-002','V_VERIFY')]:
            db.add(AttentionCase(organization_id='org-a',investor_id=iid,advisor_id='advisor-a' if iid=='A-001' else 'advisor-b',rule_id='TEST_'+priority,rule_version='1',source_date=date.today(),priority=priority,status='OPEN',title='Test review case',reason='Review example evidence',suggested_action='Verify the client record',evidence_source_row_ids=[]))
        db.commit()
    sign_in(client)
    result=client.get('/api/v1/insights/long-tail').json()
    assert result['portfolio_review_investors']==1
    assert result['verification_investors']==1
    assert result['active_flagged_investors']==2
    assert [r['investor_id'] for r in result['assigned_flagged_ranks']]==['A-001']
