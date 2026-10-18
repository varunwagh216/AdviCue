"""Populate a fresh local SQLite demo with the sample workbook and one labelled demo follow-up.

The script refuses non-SQLite connections and never deletes existing records.
Intended ONLY for a downloadable, fictional hackathon demonstration, not real clients.
Run from backend/: python -m app.scripts.seed_judge_demo
"""
from __future__ import annotations

import argparse
from datetime import date, timedelta
from pathlib import Path
from sqlalchemy import func, select

ADMIN_EMAIL = 'admin@advicue.demo'
ADVISOR_EMAIL = 'advisor@advicue.demo'
DEMO_PASSWORD = 'AdviCueDemo2026!'


def main():
    parser = argparse.ArgumentParser(description='Prepare local fictional judge-demo data without replacing anything')
    parser.add_argument('--workbook', type=Path, help='Workbook .xlsx (defaults to packaged sample_data)')
    args = parser.parse_args()

    from app.core.config import settings
    if not settings.database_url.startswith('sqlite:///'):
        parser.error('This judge demo setup is SQLite-only and never connects to cloud databases.')
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models import Organization, User, Investor
    from fastapi.testclient import TestClient
    from app.main import app

    backend = Path(__file__).resolve().parents[2]
    workbook = (args.workbook or backend.parent / 'sample_data' / 'Transaction History Investor.xlsx').resolve()
    if not workbook.is_file():
        parser.error(f'Sample workbook missing: {workbook}')

    with SessionLocal() as db:
        existing = int(db.scalar(select(func.count()).select_from(Investor)) or 0)
        admin = db.scalar(select(User).where(User.email == ADMIN_EMAIL))
        advisor = db.scalar(select(User).where(User.email == ADVISOR_EMAIL))
        if existing:
            print(f'Existing investor data ({existing} records) detected. No data was changed.')
            if admin and advisor:
                print('Demo accounts already exist; no passwords were reset.')
            return
        if admin or advisor:
            parser.error('Demo account exists but investors are empty. No change made; inspect database manually.')
        org = db.scalar(select(Organization).where(Organization.name == 'AdviCue Demo Organization'))
        if not org:
            org = Organization(name='AdviCue Demo Organization')
            db.add(org)
            db.flush()
        org.approval_required = False
        db.add_all([
            User(organization_id=org.id, name='Demo Admin', email=ADMIN_EMAIL,
                 role='SUPERVISOR', password_hash=hash_password(DEMO_PASSWORD)),
            User(organization_id=org.id, name='Demo Advisor ADV06', email=ADVISOR_EMAIL,
                 role='ADVISOR', external_advisor_code='ADV06', password_hash=hash_password(DEMO_PASSWORD)),
        ])
        db.commit()

    with TestClient(app) as client:
        origin = {'Origin': 'http://localhost:5173'}
        def login(email: str) -> dict:
            r = client.post('/api/v1/auth/login', json={'email': email, 'password': DEMO_PASSWORD}, headers=origin)
            if r.status_code != 200:
                raise RuntimeError(f'Login failed ({email}): {r.status_code} {r.text[:400]}')
            return {**origin, 'X-CSRF-Token': r.json()['csrf_token']}
        def expect(r, code: int, label: str) -> dict:
            if r.status_code != code:
                raise RuntimeError(f'{label} failed ({r.status_code}): {r.text[:600]}')
            return r.json()

        admin_headers = login(ADMIN_EMAIL)
        staged = expect(client.post('/api/v1/imports', headers=admin_headers, files={
            'file': (workbook.name, workbook.read_bytes(), 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
        }), 201, 'Sample workbook validation')
        if staged.get('error_count'):
            raise RuntimeError(f'Source validation found {staged["error_count"]} blocking errors')
        expect(client.post(f'/api/v1/imports/{staged["id"]}/commit', headers=admin_headers), 200, 'Data import')
        scan = expect(client.post('/api/v1/patterns/run', headers=admin_headers), 200, 'Pattern detection')
        if scan.get('member_count') != 8 or scan.get('advisor_count') != 6:
            raise RuntimeError(f'Unexpected pattern result: {scan}')

        advisor_headers = login(ADVISOR_EMAIL)
        cases = expect(client.get('/api/v1/attention'), 200, 'Advisor attention')['items']
        if not cases:
            raise RuntimeError('No advisor review cases found for ADV06')
        case = cases[0]
        expect(client.post(f'/api/v1/attention/{case["id"]}/actions', headers=advisor_headers,
                           json={'action': 'START_REVIEW'}), 200, 'Review action')
        recommendation = expect(client.post('/api/v1/advice', headers=advisor_headers, json={
            'alert_id': case['id'],
            'recommendation': 'ILLUSTRATIVE DEMO ONLY: Contact investor to confirm allocation and liquidity requirements.',
            'rationale': 'ILLUSTRATIVE DEMO ONLY: Portfolio belongs to a shared review pattern. No unsuitable advice is inferred.',
            'assumptions': 'No historical consultation or agreed allocation is present in the sample data.'
        }), 201, 'Demo advice draft')
        expect(client.post(f'/api/v1/advice/{recommendation["id"]}/finalize',
                           headers=advisor_headers, json={'note': 'ILLUSTRATIVE DEMO ONLY: Advisor-approved sample recommendation, not a real consultation.'}),
               200, 'Demo advisor finalization')
        task = expect(client.post('/api/v1/tasks', headers=advisor_headers, json={
            'advice_id': recommendation['id'],
            'title': 'ILLUSTRATIVE DEMO: Verify investment mandate',
            'due_date': (date.today() + timedelta(days=3)).isoformat()
        }), 201, 'Demo follow-up task')
        expect(client.post(f'/api/v1/tasks/{task["id"]}/status', headers=advisor_headers, json={
            'status': 'DONE', 'evidence_type': 'ADVISOR_ATTESTATION',
            'note': 'ILLUSTRATIVE DEMO ONLY: This is a simulated follow-up, not an actual client contact.'
        }), 200, 'Demo follow-up status')

    print('Created local judge demo database: 48 investors; detected 8 clients across 6 advisors.')
    print('Created ONE clearly labelled ILLUSTRATIVE advice and follow-up record for demonstration.')
    print(f'Advisor login: {ADVISOR_EMAIL} / {DEMO_PASSWORD}')
    print('These are PUBLIC DEMO credentials. Never use this database with real client data.')


if __name__ == '__main__':
    main()
