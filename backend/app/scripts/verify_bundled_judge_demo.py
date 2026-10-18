"""Non-destructive, fully local judge ZIP acceptance test using a *copy* of SQLite.

Run from backend: python -m app.scripts.verify_bundled_judge_demo
No live llama.cpp/Whisper inference is claimed; use Windows for those tests.
"""
from __future__ import annotations
import json,os,shutil,subprocess,sys,tempfile
from collections import Counter
from pathlib import Path
from sqlalchemy import create_engine, text


def main():
    backend=Path(__file__).resolve().parents[2]
    sqlite=backend/'advicue.db'
    if not sqlite.is_file():raise SystemExit('Packaged judge database not found')
    with tempfile.TemporaryDirectory(prefix='advicue_judge_check_') as folder:
        target=Path(folder)/'isolated.db'
        shutil.copyfile(sqlite,target)
        # Child process must load the freshly copied DB before importing app.settings.
        source='''
import json
from fastapi.testclient import TestClient
from sqlalchemy import select,func
from app.main import app
from app.core.database import SessionLocal
from app.models import Investor,Holding,InvestmentTransaction,PerformanceSnapshot,AttentionCase,MeetingNote,LocalAIBrief,CommitmentCheck,AdviceRecord
with SessionLocal() as db:
 counts={k:db.scalar(select(func.count()).select_from(t)) for k,t in {
    'investors':Investor,'holdings':Holding,'transactions':InvestmentTransaction,
    'snapshots':PerformanceSnapshot,'attention_cases_including_history':AttentionCase,
    'meeting_notes':MeetingNote,'briefs':LocalAIBrief,'commitment_checks':CommitmentCheck,'advice':AdviceRecord}.items()}
 assert counts['investors']==48 and counts['holdings']==208
 assert counts['transactions']==394 and counts['snapshots']==576
 assert counts['commitment_checks']>=1 and counts['meeting_notes']>=1
with TestClient(app) as c:
 origin={'Origin':'http://localhost:5173'}
 health=c.get('/api/v1/health');assert health.status_code==200
 auth=c.post('/api/v1/auth/login',headers=origin,json={'email':'advisor@advicue.demo','password':'AdviCueDemo2026!'})
 assert auth.status_code==200,auth.text
 own=c.get('/api/v1/investors');assert own.status_code==200
 visible={i['id'] for i in own.json()['items']}
 assert 'INV0009' in visible
 assert len(visible)==20
 assert 'INV0010' in visible
 assert 'INV0048' not in visible
 assert c.get('/api/v1/investors/INV0048/analysis').status_code==404
 a=c.get('/api/v1/investors/INV0009/analysis');assert a.status_code==200,a.text
 data=a.json();reported=data['reported_comparison']
 assert reported['negative_months']==11 and reported['observed_months']==11
 assert 'SOURCE_REPORTED' in reported['status']
 queue=c.get('/api/v1/attention');assert queue.status_code==200
 cases=queue.json()['items'];assert all(not x['superseded_by_id'] for x in cases)
 assert any(x['priority']=='P1' and x['investor_id']=='INV0009' for x in cases)
 assert any(x['priority']=='V_VERIFY' for x in cases)
 assert c.get('/api/v1/attention?include_history=true').json()['total_visible']>=len(cases)
 promises=c.get('/api/v1/investors/INV0009/commitment-checks')
 assert promises.status_code==200 and promises.json()['items']
 stats={'counts':counts,'assigned_investors':len(visible),'visible_review_cases':len(cases),
 'p1_current_cases':sum(x['priority']=='P1' for x in cases),
 'verification_cases':sum(x['priority']=='V_VERIFY' for x in cases),
 'inv0009_negative_gap_months':reported['negative_months'],
 'inv0009_summed_reported_gap_pp':reported['sum_monthly_gap_pp'],
 'illustrative_commitment_statuses':[x['status'] for x in promises.json()['items']],
 'data_scope_enforced':True,'database_tested_in_isolated_copy':True,
 'language_model_inference_tested':False,'whisper_transcription_tested':False,
 'windows_frontend_build_tested':False}
 print(json.dumps(stats,indent=2))
'''
        env={**os.environ,'DATABASE_URL':'sqlite:///'+target.as_posix(),'APP_ENV':'demo'}
        p=subprocess.run([sys.executable,'-c',source],cwd=backend,env=env,capture_output=True,text=True,timeout=55)
        if p.returncode:
            print(p.stderr,file=sys.stderr)
            raise SystemExit('Isolated judge API acceptance failed: '+p.stdout)
        print(p.stdout)

if __name__=='__main__':main()
