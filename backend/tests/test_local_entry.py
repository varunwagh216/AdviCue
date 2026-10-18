from fastapi.testclient import TestClient
from sqlalchemy import select
from app.main import app
from app.core.database import SessionLocal
from app.models import User

def local_client():
    return TestClient(app, client=('127.0.0.1', 50000))

def test_button_opens_assigned_advisor_and_session():
    with local_client() as c:
        response=c.post('/api/v1/auth/enter',headers={'Origin':'http://localhost:5173'})
        assert response.status_code==200,response.text
        assert response.json()['user']['id']=='advisor-a'
        assert response.json()['csrf_token']
        assert c.get('/api/v1/auth/me').status_code==200
        token=response.json()['csrf_token']
        assert c.post('/api/v1/auth/logout',headers={'X-CSRF-Token':token}).status_code==200
        assert c.get('/api/v1/auth/me').status_code==401

def test_remote_and_untrusted_origin_blocked():
    with TestClient(app,client=('192.168.1.42',50000)) as c:
        assert c.post('/api/v1/auth/enter').status_code==403
    with local_client() as c:
        assert c.post('/api/v1/auth/enter',headers={'Origin':'https://untrusted.example'}).status_code==403

def test_missing_or_disabled_account_not_replaced():
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.id=='advisor-a'))
        user.is_active=False;db.commit()
    with local_client() as c:assert c.post('/api/v1/auth/enter').status_code==403
    with SessionLocal() as db:
        user=db.get(User,'advisor-a');user.email='other@advicue.local';db.commit()
    with local_client() as c:assert c.post('/api/v1/auth/enter').status_code==503
