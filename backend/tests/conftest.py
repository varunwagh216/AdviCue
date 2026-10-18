import os
import tempfile
from pathlib import Path

DB_FILE = Path(tempfile.mkdtemp(prefix="advicue_phase1_tests_")) / "test.db"
os.environ["DATABASE_URL"] = f"sqlite:///{DB_FILE}"
os.environ["FRONTEND_ORIGIN"] = "http://localhost:5173"

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.core.database import Base, SessionLocal, engine
import app.models  # noqa: F401
from app.core.security import hash_password
from app.main import app
from app.models import Organization, User, Investor


@pytest.fixture(autouse=True)
def reset_db():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    with SessionLocal() as db:
        org1 = Organization(id="org-a", name="Organization A")
        org2 = Organization(id="org-b", name="Organization B")
        db.add_all([org1, org2])
        users = [
            User(id="advisor-a", organization_id="org-a", name="Advisor A", email="advisor@advicue.local", password_hash=hash_password("ExamplePassword123!"), role="ADVISOR"),
            User(id="advisor-b", organization_id="org-a", name="Advisor B", email="b@advicue.local", password_hash=hash_password("ExamplePassword123!"), role="ADVISOR"),
            User(id="supervisor-a", organization_id="org-a", name="Supervisor A", email="supervisor@advicue.local", password_hash=hash_password("ExamplePassword123!"), role="SUPERVISOR"),
            User(id="supervisor-c", organization_id="org-b", name="Supervisor C", email="supervisor-c@advicue.local", password_hash=hash_password("ExamplePassword123!"), role="SUPERVISOR"),
            User(id="advisor-c", organization_id="org-b", name="Advisor C", email="c@advicue.local", password_hash=hash_password("ExamplePassword123!"), role="ADVISOR"),
        ]
        db.add_all(users)
        db.add_all([
            Investor(id="A-001", organization_id="org-a", advisor_id="advisor-a", display_name="Test Investor A", risk_profile="Moderate"),
            Investor(id="A-002", organization_id="org-a", advisor_id="advisor-b", display_name="Test Investor B", risk_profile="Conservative"),
            Investor(id="B-001", organization_id="org-b", advisor_id="advisor-c", display_name="Test Investor C", risk_profile="Moderate"),
        ])
        db.commit()
    yield


@pytest.fixture
def client():
    with TestClient(app) as client:
        yield client


def sign_in(client, email="advisor@advicue.local", password="ExamplePassword123!"):
    response=client.post("/api/v1/auth/login",json={"email":email,"password":password}, headers={"Origin":"http://localhost:5173"})
    assert response.status_code == 200, response.text
    return response.json()
