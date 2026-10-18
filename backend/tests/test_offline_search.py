from datetime import date
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace as NS
from unittest.mock import patch
import io,json,wave
import pytest
from app.core.database import SessionLocal
from app.models import InvestmentTransaction,SourceRow,ImportBatch
from app.ai.local_models import LocalModelError
from tests.conftest import sign_in

def headers(client):return {'Origin':'http://localhost:5173','X-CSRF-Token':sign_in(client)['csrf_token']}

def transactions():
    with SessionLocal() as db:
        db.add(ImportBatch(id='batch',organization_id='org-a',uploaded_by='advisor-a',filename='test.csv',file_sha256='a'*64,status='COMMITTED'));db.flush()
        for i,(cid,duplicate,confidence,kind,amount) in enumerate([('A-001',False,'VERIFIED','SIP',1000),('A-001',False,'VERIFIED','sip',2000),('A-001',True,'VERIFIED','SIP',999),('A-001',False,'QUARANTINED_AMBIGUOUS','SIP',999),('A-001',False,'VERIFIED','BUY',999),('A-002',False,'VERIFIED','SIP',8888),('B-001',False,'VERIFIED','SIP',8888)]):
            org='org-b' if cid=='B-001' else 'org-a';source=SourceRow(id=f's{i}',batch_id='batch',sheet_name='Transactions',row_number=i+2,raw_data={},normalized_data={});db.add(source);db.flush()
            db.add(InvestmentTransaction(id=f't{i}',organization_id=org,investor_id=cid,source_row_id=source.id,external_transaction_id=f't{i}',date=date(2026,1,1),type=kind,instrument_name='Fund',asset_class='Equity Mutual Fund',amount=Decimal(amount),possible_duplicate=duplicate,date_confidence=confidence))
        db.commit()

@pytest.mark.parametrize('query',['how many profiles have sips','How many clients have SIPs?','List investors with systematic investments','What is the total SIP?'])
def test_sip_counts_distinct_assigned_clients_not_transactions(client,query):
    transactions();h=headers(client)
    with patch('app.api.workspace.local_llm_json',return_value={'intent':'ADVICE','client_search':''}):r=client.post('/api/v1/assistant/search',json={'query':query},headers=h)
    assert r.status_code==200,r.text
    data=r.json();assert data['intent']=='SIPS' and data['matched_count']==1 and Decimal(data['total_recorded_sip'])==3000
    assert len(data['items'])==1 and data['items'][0]['client_name']=='Test Investor A'
    assert '8888' not in str(data) and 'active mandate' in data['note']

@pytest.mark.parametrize('query',['Which clients need my attention?','Show my reviews','Show my follow-ups'])
def test_workflow_questions_are_not_replaced_by_book_counts(client,query):
    h=headers(client)
    with patch('app.api.workspace.local_llm_json',return_value={'intent':'CLIENT','client_search':''}):data=client.post('/api/v1/assistant/search',json={'query':query},headers=h).json()
    assert data['intent'] in ('ATTENTION','REVIEWS','FOLLOW_UPS')

@pytest.mark.parametrize('query',['How many profiles have insurance?','How many profiles have loans?','How many SIPs last month?','Show clients with equity above 10000','How many SIPs above 5000?','Does Rahul have SIPs?','Show INV0048 SIPs'])
def test_unsupported_filters_request_clarification(client,query):
    h=headers(client)
    with patch('app.api.workspace.local_llm_json',side_effect=LocalModelError('offline')):data=client.post('/api/v1/assistant/search',json={'query':query},headers=h).json()
    assert data['intent']=='CLARIFY' and data['items']==[]

def wav_bytes(seconds=1,rate=16000,channels=1):
    out=io.BytesIO()
    with wave.open(out,'wb') as w:w.setparams((channels,2,rate,0,'NONE','not compressed'));w.writeframes(b'\0\0'*int(rate*channels*seconds))
    return out.getvalue()

def test_voice_transcript_is_not_saved_as_meeting(client):
    from sqlalchemy import func,select
    from app.models import MeetingNote
    h=headers(client)
    with patch('app.ai.local_models.transcribe_audio_locally',return_value='How many clients have SIPs?') as call:r=client.post('/api/v1/assistant/transcribe',headers=h,files={'audio':('question.wav',wav_bytes(),'audio/wav')})
    assert r.status_code==200,r.text
    assert r.json()['provider']=='whisper.cpp' and call.call_args.args[1]=='.wav'
    with SessionLocal() as db:assert db.scalar(select(func.count()).select_from(MeetingNote))==0

def test_voice_requires_auth_csrf_valid_duration_and_installed_assets(client):
    assert client.post('/api/v1/assistant/transcribe',files={'audio':('a.wav',wav_bytes())}).status_code==401
    h=headers(client)
    assert client.post('/api/v1/assistant/transcribe',headers={'Origin':h['Origin']},files={'audio':('a.wav',wav_bytes())}).status_code==403
    assert client.post('/api/v1/assistant/transcribe',headers=h,files={'audio':('a.wav',b'garbage')}).status_code==415
    assert client.post('/api/v1/assistant/transcribe',headers=h,files={'audio':('a.wav',wav_bytes(47))}).status_code==415
    with patch('app.ai.local_models.transcribe_audio_locally',side_effect=LocalModelError('Assets missing. No download was attempted.')):r=client.post('/api/v1/assistant/transcribe',headers=h,files={'audio':('a.wav',wav_bytes())})
    assert r.status_code==503 and 'No download' in r.text

@pytest.mark.parametrize('rate,channels',[(16000,1),(22050,1),(44100,2)])
def test_whisper_runs_local_paths_and_removes_temporary_audio(monkeypatch,tmp_path,rate,channels):
    from app.ai import speech
    exe=tmp_path/'whisper-cli.exe';exe.write_bytes(b'exe');model=tmp_path/'ggml-base.bin';model.write_bytes(b'model')
    monkeypatch.setattr(speech,'speech_assets',lambda:(exe,model));paths=[]
    def run(args,**kwargs):
        assert args[0]==str(exe) and '-m' in args and '-ng' in args
        with wave.open(args[args.index('-f')+1],'rb') as audio:assert audio.getframerate()==16000 and audio.getnchannels()==1
        output=Path(args[args.index('-of')+1]);paths.append(output.parent)
        output.with_suffix('.json').write_text(json.dumps({'transcription':[{'text':' How many clients have SIPs?'}]}),encoding='utf-8');return NS(returncode=0)
    monkeypatch.setattr(speech.subprocess,'run',run)
    assert speech.transcribe(wav_bytes(rate=rate,channels=channels),'.wav')=='How many clients have SIPs?'
    assert not paths[0].exists()

def test_whisper_fails_closed_when_model_missing(monkeypatch,tmp_path):
    from app.ai import speech
    monkeypatch.setattr(speech,'speech_assets',lambda:(tmp_path/'missing',tmp_path/'missing.bin'))
    with pytest.raises(LocalModelError,match='No download'):speech.transcribe(wav_bytes(),'.wav')

def test_no_external_docs_cdn_or_api_fallback(client):
    assert 'cdn.jsdelivr.net' not in client.get('/docs').text
    assert client.get('/api/v1/does-not-exist').status_code==404
    assert "connect-src 'self'" in client.get('/api/v1/health').headers['content-security-policy']
