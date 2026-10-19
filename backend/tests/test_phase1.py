from datetime import datetime, timedelta, timezone
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models import AuditEvent, LoginSession, User
from app.core.security import verify_password
from tests.conftest import sign_in


def test_public_health_uses_db(client, monkeypatch):
    monkeypatch.setenv("ADVICUE_INSTANCE_ID", "health-test-instance")
    response=client.get("/api/v1/health")
    assert response.status_code==200
    assert response.json()=={"status":"ok", "service":"advicue-ai", "phase":9, "database":"connected", "edition":"AdviCue AI", "instance_id":"health-test-instance"}


def test_protected_dashboard_requires_login(client):
    assert client.get("/api/v1/dashboard").status_code==401
    assert client.get("/api/v1/investors").status_code==401


def test_sign_in_then_dashboard_and_me(client):
    payload=sign_in(client)
    assert payload["user"]["role"]=="ADVISOR"
    assert payload["csrf_token"]
    assert "advicue_session" in client.cookies
    assert client.get("/api/v1/dashboard").json()["investor_count"]==1
    user=client.get("/api/v1/auth/me")
    assert user.status_code==200 and user.json()["csrf_token"]
    assert user.json()["user"]["email"]=="advisor@advicue.local"


def test_invalid_login_does_not_authenticate(client):
    r=client.post("/api/v1/auth/login", json={"email":"advisor@advicue.local","password":"bad"})
    assert r.status_code==401
    assert r.json()["detail"]=="Invalid email or password"
    assert client.get("/api/v1/dashboard").status_code==401


def test_bad_origin_rejected(client):
    r=client.post("/api/v1/auth/login", json={"email":"advisor@advicue.local","password":"ExamplePassword123!"},headers={"Origin":"https://attacker.invalid"})
    assert r.status_code==403


def test_csrf_required_to_logout(client):
    credentials=sign_in(client)
    assert client.post("/api/v1/auth/logout").status_code==403
    assert client.post("/api/v1/auth/logout",headers={"X-CSRF-Token":"wrong"}).status_code==403
    assert client.post("/api/v1/auth/logout",headers={"X-CSRF-Token":credentials["csrf_token"]}).status_code==200
    assert client.get("/api/v1/dashboard").status_code==401


def test_csrf_is_stable_on_session_restore(client):
    credentials=sign_in(client)
    new_token=client.get("/api/v1/auth/me").json()["csrf_token"]
    assert new_token == credentials["csrf_token"]
    assert client.post("/api/v1/auth/logout",headers={"X-CSRF-Token":new_token}).status_code==200


def test_investors_scoped_to_advisor(client):
    sign_in(client)
    investor_ids=[i["id"] for i in client.get("/api/v1/investors").json()["items"]]
    assert investor_ids==["A-001"]


def test_supervisor_only_sees_own_organization(client):
    sign_in(client,"supervisor@advicue.local")
    investor_ids=[i["id"] for i in client.get("/api/v1/investors").json()["items"]]
    assert investor_ids==["A-001","A-002"]


def test_other_organization_isolated(client):
    sign_in(client,"c@advicue.local")
    ids=[i["id"] for i in client.get("/api/v1/investors").json()["items"]]
    assert ids==["B-001"]


def test_expired_session_rejected(client):
    sign_in(client)
    with SessionLocal() as db:
        record=db.scalars(select(LoginSession)).first()
        record.expires_at=datetime.now(timezone.utc)-timedelta(minutes=1)
        db.commit()
    assert client.get("/api/v1/dashboard").status_code==401


def test_password_is_hashed_and_auth_is_audited(client):
    with SessionLocal() as db:
        user=db.get(User,"advisor-a")
        assert "ExamplePassword" not in user.password_hash
        assert verify_password(user.password_hash,"ExamplePassword123!")
    sign_in(client)
    with SessionLocal() as db:
        assert db.scalars(select(AuditEvent).where(AuditEvent.action=="AUTH_LOGIN")).first()


def test_api_docs_exist(client):
    assert client.get("/docs").status_code==200
    assert client.get("/openapi.json").status_code==200
