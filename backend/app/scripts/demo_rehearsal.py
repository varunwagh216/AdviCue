"""Create a NEW, isolated demo DB and exercise the complete evidence-to-action loop.

Never points to or modifies the normal advicue.db. Uses the supplied workbook for
source observations and clearly marks new advice/tasks as ILLUSTRATIVE DEMO.

Example (from backend):
python -m app.scripts.demo_rehearsal --workbook "..\\Transaction History Investor.xlsx" --output-db "..\\demo\\advicue_rehearsal.db"
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import secrets
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


def main():
    parser=argparse.ArgumentParser(description='Run end-to-end demo in a fresh isolated SQLite database')
    parser.add_argument('--workbook',type=Path,required=True,help='Original investor workbook (.xlsx)')
    parser.add_argument('--output-db',type=Path,required=True,help='NEW SQLite sandbox path; refuses existing files')
    parser.add_argument('--report',type=Path,help='Optional destination for JSON rehearsal summary')
    args=parser.parse_args()
    workbook=args.workbook.expanduser().resolve()
    sandbox=args.output_db.expanduser().resolve()
    if not workbook.is_file() or workbook.suffix.lower()!='.xlsx':
        parser.error('Provide a readable .xlsx workbook')
    if sandbox.exists():
        parser.error('Sandbox already exists. Refusing overwrite: '+str(sandbox))
    backend=Path(__file__).resolve().parents[2]
    actual_db=(backend/'advicue.db').resolve()
    if sandbox==actual_db:
        parser.error('Refusing to use the production/development database')
    if args.report and args.report.expanduser().resolve()==sandbox:
        parser.error('Report path must differ from sandbox database')
    sandbox.parent.mkdir(parents=True,exist_ok=True)
    env={**os.environ,'DATABASE_URL':f'sqlite:///{sandbox.as_posix()}',
         'FRONTEND_ORIGIN':'http://localhost:5173'}
    migrations=subprocess.run([sys.executable,'-m','alembic','upgrade','head'],
                               cwd=str(backend),env=env,capture_output=True,text=True)
    if migrations.returncode:
        print(migrations.stdout,migrations.stderr,file=sys.stderr)
        raise SystemExit('Sandbox migration failed; normal database was not touched.')
    # Only now import app modules, after overriding the database configuration.
    os.environ['DATABASE_URL']=env['DATABASE_URL']
    os.environ['FRONTEND_ORIGIN']=env['FRONTEND_ORIGIN']
    from fastapi.testclient import TestClient
    from sqlalchemy import select
    from app.main import app
    from app.core.database import SessionLocal
    from app.core.security import hash_password
    from app.models import Organization, User

    SUP='phase9-supervisor@advicue.local'; ADV='phase9-advisor@advicue.local'
    password=secrets.token_urlsafe(24)
    with SessionLocal() as db:
        org=Organization(name='AdviCue PHASE9 SANDBOX - NOT REAL CLIENT ADVICE')
        db.add(org);db.flush()
        db.add_all([
            User(organization_id=org.id,name='Demo Supervisor',email=SUP,role='SUPERVISOR',password_hash=hash_password(password)),
            User(organization_id=org.id,name='Demo Advisor ADV06',email=ADV,role='ADVISOR',external_advisor_code='ADV06',password_hash=hash_password(password)),
        ]);db.commit()

    def must(response, expected=200, what='API'):
        if response.status_code!=expected:
            raise RuntimeError(f'{what}: HTTP {response.status_code}, {response.text[:1000]}')
        return response.json()
    with TestClient(app) as client:
        origin={'Origin':'http://localhost:5173'}
        def login(email):
            reply=must(client.post('/api/v1/auth/login',headers=origin,json={'email':email,'password':password}),what='Login')
            return {'X-CSRF-Token':reply['csrf_token'],**origin}
        sup=login(SUP)
        staged=must(client.post('/api/v1/imports',headers=sup,
             files={'file':(workbook.name,workbook.read_bytes(),'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')}),201,'Workbook validation')
        if staged['error_count']:
            raise RuntimeError(f'Workbook has {staged["error_count"]} blocking validation errors; no commit was made.')
        must(client.post(f'/api/v1/imports/{staged["id"]}/commit',headers=sup),what='Workbook commit')
        pattern=must(client.post('/api/v1/patterns/run',headers=sup),what='Pattern detection')
        if not pattern['matched']:
            raise RuntimeError('The supplied workbook did not produce the target cross-client finding.')
        full=must(client.get('/api/v1/patterns'),what='Pattern list')
        matching=set()
        for obj in full['items']:
            matching.update(x['investor_id'] for x in obj['members'])
        if matching!=set(f'INV{i:04d}' for i in range(9,17)):
            raise RuntimeError(f'Unexpected pattern members: {sorted(matching)}')
        advisor=login(ADV)
        cases=must(client.get('/api/v1/attention'),what='Advisor attention')['items']
        assigned=next((c for c in cases if c['investor_id'] in matching),None)
        if not assigned:
            raise RuntimeError('ADV06 has no assigned review case; verify workbook advisor assignments')
        must(client.post(f"/api/v1/attention/{assigned['id']}/actions",headers=advisor,json={'action':'START_REVIEW'}),what='Start review')
        advice=must(client.post('/api/v1/advice',headers=advisor,json={
            'alert_id':assigned['id'],
            'recommendation':'ILLUSTRATIVE DEMO: Contact investor to verify their mandate, allocation and liquidity needs.',
            'rationale':'ILLUSTRATIVE DEMO: Source holdings show a review pattern; no unsuitable advice or loss is inferred.',
            'assumptions':'No historical mandate or client consultation is asserted.'}),201,'Advice draft')
        must(client.post(f"/api/v1/advice/{advice['id']}/submit",headers=advisor),what='Advice submit')
        sup=login(SUP)
        must(client.post(f"/api/v1/advice/{advice['id']}/approve",headers=sup,
             json={'note':'ILLUSTRATIVE DEMO APPROVAL: review only, not trading authorization.'}),what='Advice approval')
        advisor=login(ADV)
        task=must(client.post('/api/v1/tasks',headers=advisor,json={
            'advice_id':advice['id'],'title':'ILLUSTRATIVE DEMO: Confirm client mandate',
            'due_date':str(date.today()+timedelta(days=2))}),201,'Follow-up task')
        done=must(client.post(f"/api/v1/tasks/{task['id']}/status",headers=advisor,json={
            'status':'DONE', 'evidence_type':'ADVISOR_ATTESTATION',
            'note':'ILLUSTRATIVE DEMO ONLY: this simulated completed follow-up is NOT evidence of an actual client contact.'}),what='Follow-up completion')
        ready=must(client.get('/api/v1/demo/readiness'),what='Demo readiness')
    report={
        'created_at':datetime.now(timezone.utc).isoformat(),
        'mode':'ISOLATED DEMONSTRATION ONLY',
        'workbook_filename':workbook.name,
        'source_sheet_counts':staged['sheet_counts'],
        'validation_warning_count':staged['warning_count'],
        'pattern':{'matched':pattern['matched'],'member_count':pattern['member_count'],
                   'advisor_count':pattern['advisor_count'],'recorded_value_total':pattern['recorded_value_total'],
                   'matched_investor_ids':sorted(matching)},
        'illustrative_actions':{'case_id':assigned['id'],'advice_id':advice['id'],
                                'follow_up_id':task['id'],'task_status':done['status'],
                                'advice_and_task_are_fictional':True},
        'advisor_readiness':{'ready_count':ready['ready_count'],'total_checks':ready['total_checks'],
                             'all_recorded_evidence':ready['workflow_evidence_ready']},
        'ai_inference_tested':False,
        'normal_database_modified':False,
        'warning':'This sandbox intentionally contains simulated advice and follow-ups. Never present them as real historical client interactions.'
    }
    if args.report:
        dest=args.report.expanduser().resolve();dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_text(json.dumps(report,indent=2,ensure_ascii=False),encoding='utf-8')
    print(json.dumps(report,indent=2,ensure_ascii=False))
    print('Isolated sandbox database:',sandbox)
    print('Temporary sandbox-only demo accounts:', SUP, ADV)
    print('Temporary sandbox-only demo password:', password)
    if args.report:print('Isolated demo report:',dest)

if __name__=='__main__':main()
