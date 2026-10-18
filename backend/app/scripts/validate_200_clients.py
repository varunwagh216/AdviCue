"""Reproducible synthetic 200-client functional/latency check; never uses the demo DB.

python -m app.scripts.validate_200_clients --output ../docs/BOOK_200_VALIDATION.json
This is controlled scenario coverage, not a field study or capacity certification.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from time import perf_counter
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal as D


def performance(iid, today, amount='100000', lag=False):
    start=today-timedelta(days=30);value=D(amount)
    return dict(client_id=iid,illustrative=True,currency='INR',flow_statement_reference='synthetic/complete-flow-ledger',valuation_coverage_reference='synthetic/all-boundaries',flows_complete=True,valuation_coverage_complete=True,boundaries_include_all_flows_and_rebalances=True,fees_taxes_consistent=True,
        benchmark_policy=dict(name='Synthetic balanced benchmark',rationale='Synthetic comparison for controlled arithmetic testing only.',source_reference='synthetic/benchmark-policy',client_mandate_reference='synthetic/client-mandate',effective_from=start.isoformat(),effective_to=today.isoformat(),suitable_for_client=True),
        periods=[dict(start_date=start.isoformat(),end_date=today.isoformat(),start_value=str(value),end_value=str(value),flows=[],classes=[dict(asset_class=c,start_value=str(value*w),end_value=str(value*w),net_flow='0',benchmark_weight_pct='50',benchmark_return_pct=('10' if lag and c=='Direct Equity' else '0'),valuation_reference='synthetic/'+c+'/valuations',benchmark_reference='synthetic/'+c+'/benchmark') for c,w in [('Direct Equity',D('.4')),('Fixed Deposit',D('.6'))]])])


def worker(output,live_ai=False,audio=None):
    from fastapi.testclient import TestClient
    from sqlalchemy import select,func
    from app.core.database import Base,engine,SessionLocal
    from app.core.security import hash_password
    from app.main import app
    from app.models import Organization,User,Investor,ImportBatch,SourceRow,Holding,FollowUpTask,GoalPlan,ReviewEvidence,AttentionCase
    from app.engines.evidence import PerformanceEvidence,reconcile
    from app.services.monitoring import refresh_clients
    Base.metadata.create_all(engine);today=date.today();expected={};calculation_count=0
    with SessionLocal() as db:
        db.add_all([Organization(id='synthetic',name='Synthetic validation only'),Organization(id='outside',name='Other organization')]);db.flush()
        db.add_all([User(id='synthetic-advisor',organization_id='synthetic',name='Synthetic Advisor',email='synthetic@invalid.local',password_hash=hash_password('SyntheticValidation123!'),role='ADVISOR'),User(id='outside-advisor',organization_id='outside',name='Outside Advisor',email='outside@invalid.local',password_hash=hash_password('SyntheticValidation123!'),role='ADVISOR')]);db.flush()
        db.add(ImportBatch(id='synthetic-batch',organization_id='synthetic',uploaded_by='synthetic-advisor',filename='GENERATED_SYNTHETIC_NOT_PROVIDER_DATA',file_sha256='0'*64,status='COMMITTED'));db.flush()
        codes=['APPROVED_TARGET_DRIFT','STALE_VALUATION','OVERDUE_COMMITMENT','GOAL_FUNDING_GAP','RECONCILED_BENCHMARK_LAG',None]
        for i in range(200):
            iid=f'SYN{i+1:04d}';family=i%6;amount=D(100000+i*100);expected[iid]={codes[family]} if codes[family] else set()
            inv=Investor(id=iid,organization_id='synthetic',advisor_id='synthetic-advisor',display_name=f'Synthetic Client {i+1:03d}',risk_profile=['Conservative','Moderate','Aggressive'][i%3],primary_goal=['Retirement','Education','Liquidity','Wealth creation'][i%4],goal_target_amount=D('100000000') if family==3 else None,goal_target_date=today+timedelta(days=365) if family==3 else None)
            db.add(inv);db.flush()
            for j,(name,weight) in enumerate([('Direct Equity',D('.9') if family==0 else D('.4')),('Fixed Deposit',D('.1') if family==0 else D('.6'))]):
                sid=f'row-{i}-{j}';db.add(SourceRow(id=sid,batch_id='synthetic-batch',sheet_name='Holdings',row_number=i*2+j+1,raw_data={'synthetic':True}));db.flush()
                db.add(Holding(organization_id='synthetic',investor_id=iid,source_row_id=sid,external_holding_id=sid,as_of_date=today-timedelta(days=60) if family==1 else today,asset_class=name,instrument_name=f'Synthetic {name}',current_value=amount*weight))
            mandate=dict(client_id=iid,illustrative=True,effective_from=(today-timedelta(days=90)).isoformat(),effective_to=(today+timedelta(days=90)).isoformat(),source_reference='synthetic/mandate',rationale='Synthetic bands for rule validation only.',liquidity_context='Synthetic test',bands=[dict(asset_class='Direct Equity',min_pct='20',max_pct='60'),dict(asset_class='Fixed Deposit',min_pct='40',max_pct='80')])
            def evidence(kind,payload):
                db.add(ReviewEvidence(organization_id='synthetic',investor_id=iid,advisor_id='synthetic-advisor',kind=kind,status='APPROVED',payload=payload,payload_sha256=hashlib.sha256(json.dumps(payload,sort_keys=True).encode()).hexdigest(),approved_at=datetime.now(timezone.utc),approval_note='Controlled synthetic validation; no provider verification.'))
            evidence('MANDATE',mandate)
            p=performance(iid,today,str(amount),family==4);r=reconcile(PerformanceEvidence.model_validate(p));calculation_count+=1
            assert abs(sum(D(c['total_pp']) for c in r['class_contributions'])-D(r['active_return_pp']))<D('.00001')
            evidence('PERFORMANCE',p)
            if family==2:db.add(FollowUpTask(organization_id='synthetic',investor_id=iid,owner_id='synthetic-advisor',title='Synthetic overdue commitment',due_date=today-timedelta(days=2),status='OPEN'))
            if family==3:db.add(GoalPlan(organization_id='synthetic',investor_id=iid,advisor_id='synthetic-advisor',principal=amount,monthly_contribution=D('100'),as_of_date=today,annual_rates=['4','8','12']))
        db.add(Investor(id='OUTSIDE',organization_id='outside',advisor_id='outside-advisor',display_name='Outside sentinel'));db.commit()
        advisor=db.get(User,'synthetic-advisor');started=perf_counter();result=refresh_clients(db,advisor);refresh_seconds=perf_counter()-started
        observed={iid:set() for iid in expected}
        for item in result['items']:observed[item['investor_id']].update(item['rules'])
        mismatches={iid:{'expected':sorted(expected[iid]),'observed':sorted(observed[iid])} for iid in expected if expected[iid]!=observed[iid]}
        assert not mismatches,mismatches
        case_count=db.scalar(select(func.count()).select_from(AttentionCase));again=refresh_clients(db,advisor)
        assert again['cases_created']==0
        assert db.scalar(select(func.count()).select_from(AttentionCase))==case_count
        from unittest.mock import patch
        class Tomorrow(date):
            @classmethod
            def today(cls):return today+timedelta(days=1)
        with patch('app.services.monitoring.date',Tomorrow):next_day=refresh_clients(db,advisor)
        assert next_day['cases_created']==0
    latencies=[];ai_results=None
    with TestClient(app) as client:
        login=client.post('/api/v1/auth/login',json={'email':'synthetic@invalid.local','password':'SyntheticValidation123!'},headers={'Origin':'http://localhost:5173'});assert login.status_code==200,login.text
        assert len(client.get('/api/v1/investors').json()['items'])==200
        for iid in expected:
            start=perf_counter();response=client.get(f'/api/v1/investors/{iid}/analysis');latencies.append((perf_counter()-start)*1000)
            assert response.status_code==200,response.text
            assert client.get(f'/api/v1/investors/{iid}/verified-analysis').json()['status']=='ILLUSTRATIVE_RECONCILED'
        for suffix in ('analysis','evidence','verified-analysis','timeline'):
            assert client.get('/api/v1/investors/OUTSIDE/'+suffix).status_code==404
        assert client.get('/api/v1/pilot/summary').json()['reviews_completed']==0
        assert client.get('/api/v1/home').json()['assigned_clients']==200
        if live_ai:
            headers={'Origin':'http://localhost:5173','X-CSRF-Token':login.json()['csrf_token']}
            brief_timings=[]
            for iid in ['SYN0001','SYN0002','SYN0003','SYN0004','SYN0005','SYN0006']:
                started=perf_counter();brief=client.post('/api/v1/ai/briefs',headers=headers,json={'investor_id':iid})
                assert brief.status_code==201,(iid,brief.text)
                brief_timings.append(round(perf_counter()-started,3))
            transcript='This is a synthetic test meeting. The client prefers a cash reserve for education expenses. The advisor will review the contribution plan next Friday. No investment return was promised.'
            note=client.post('/api/v1/meetings/notes',headers=headers,json={'investor_id':'SYN0001','transcript':transcript});assert note.status_code==201,note.text
            extracted=client.post('/api/v1/meetings/'+note.json()['id']+'/extract',headers=headers)
            assert extracted.status_code==200,extracted.text
            draft=extracted.json();assert draft['status']=='DRAFT' and draft['extracted_draft']['coverage']['complete']
            commitments=draft['extracted_draft']['commitments'];assert any('review' in x.lower() and 'contribution' in x.lower() for x in commitments),commitments
            ai_results={'actual_llama_brief_api':'passed','brief_clients':6,'brief_seconds':brief_timings,'actual_meeting_extraction_api':'passed','explicit_commitment_captured':True,'note_remains_unapproved':True}
            for query,expected_intent in [('Show SYN0001 portfolio','CLIENT'),('Which clients need my attention?','ATTENTION'),('Show my follow-ups','FOLLOW_UPS')]:
                response=client.post('/api/v1/assistant/search',headers=headers,json={'query':query})
                assert response.status_code==200,response.text
                answer=response.json();assert answer['mode']=='LOCAL_AI' and answer['intent']==expected_intent and answer['items'],answer
            ai_results['actual_home_search_requests']=3
            if audio:
                import re
                response=client.post('/api/v1/meetings/transcribe',headers=headers,data={'investor_id':'SYN0001','recording_consent':'true'},files={'audio':('synthetic-meeting.wav',audio.read_bytes(),'audio/wav')})
                assert response.status_code==201,response.text
                words=lambda s:re.findall(r'[a-z]+',s.lower())
                reference=words(transcript);actual=words(response.json()['transcript']);previous=list(range(len(actual)+1))
                for i,word in enumerate(reference,1):
                    current=[i]
                    for j,other in enumerate(actual,1):current.append(min(current[-1]+1,previous[j]+1,previous[j-1]+(word!=other)))
                    previous=current
                wer=previous[-1]/len(reference)
                assert wer<=.25,wer
                ai_results.update(actual_whisper_upload_api='passed',synthetic_word_error_rate=round(wer,4),reference_words=len(reference),transcribed_words=len(actual),speech_scope='One generated English speech sample; not representative human speech or accuracy certification.')
    latencies.sort();true_labels=sum(len(s) for s in expected.values())
    report=dict(generated_at=datetime.now(timezone.utc).isoformat(),passed=True,book_clients=200,other_organization_sentinels=1,scenarios={'mandate_drift':34,'stale_valuation':34,'overdue_commitment':33,'goal_gap':33,'benchmark_lag':33,'no_trigger':33},expected_rule_matches=true_labels,unexpected_rule_matches=0,missed_rule_matches=0,arithmetic_reconciliations=calculation_count,refresh_seconds=round(refresh_seconds,3),repeat_refresh_new_cases=again['cases_created'],client_analysis_latency_ms={'p50':round(latencies[len(latencies)//2],2),'p95':round(latencies[int(len(latencies)*.95)-1],2),'max':round(max(latencies),2)},scope_checks_passed=4,pilot_results_created=0,limitations='Generated controlled scenarios on one local machine. No live investor/provider data. Does not measure real-world false positives, advisor retention, concurrency capacity or advice outcomes.')
    report['next_day_refresh_new_cases']=next_day['cases_created']
    if ai_results:report['local_ai_workflow']=ai_results
    output.write_text(json.dumps(report,indent=2),encoding='utf-8');print(json.dumps(report,indent=2))


def main():
    p=argparse.ArgumentParser();p.add_argument('--output',type=Path,default=Path('../docs/BOOK_200_VALIDATION.json'));p.add_argument('--worker',action='store_true');p.add_argument('--live-ai',action='store_true');p.add_argument('--synthetic-audio',type=Path,help='Only the documented generated English test speech, not a private recording');args=p.parse_args();output=args.output.resolve();output.parent.mkdir(parents=True,exist_ok=True)
    if args.worker:worker(output,args.live_ai,args.synthetic_audio);return
    with tempfile.TemporaryDirectory(prefix='advicue_synthetic_200_') as directory:
        env=os.environ.copy();env['DATABASE_URL']='sqlite:///'+str(Path(directory)/'synthetic.db');env['FRONTEND_ORIGIN']='http://localhost:5173'
        command=[sys.executable,'-m','app.scripts.validate_200_clients','--worker','--output',str(output)]
        if args.live_ai:command.append('--live-ai')
        if args.synthetic_audio:command.extend(['--synthetic-audio',str(args.synthetic_audio.resolve())])
        output.write_text(json.dumps({'passed':False,'status':'RUNNING'}),encoding='utf-8')
        try:subprocess.run(command,env=env,check=True)
        except subprocess.CalledProcessError:
            output.write_text(json.dumps({'passed':False,'status':'FAILED','detail':'Validation failed; inspect the terminal assertion. No success report was retained.'}),encoding='utf-8')
            raise


if __name__=='__main__':main()
