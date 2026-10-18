"""Phase 7/8: consent, tenancy, human approval, local-only model and provenance."""
from datetime import date
from decimal import Decimal
from unittest.mock import patch
from dataclasses import replace
from app.core.config import settings

from sqlalchemy import select
from app.core.database import SessionLocal
from app.models import Holding, ImportBatch, SourceRow, LocalAIBrief, MeetingNote
from app.ai.local_models import local_llama_cpp_url, LocalModelError
from tests.conftest import sign_in

ORIGIN = {'Origin':'http://localhost:5173'}


def auth(csrf): return {**ORIGIN,'X-CSRF-Token':csrf}


def test_manual_note_requires_auth_csrf_and_advisor(client):
    c=sign_in(client)['csrf_token']
    payload={'investor_id':'A-001','transcript':'Discussed the possibility of reviewing cash needs before changing investment allocations.'}
    assert client.post('/api/v1/meetings/notes',json=payload,headers=ORIGIN).status_code==403
    assert client.post('/api/v1/meetings/notes',json={**payload,'investor_id':'A-002'},headers=auth(c)).status_code==404
    created=client.post('/api/v1/meetings/notes',json=payload,headers=auth(c))
    assert created.status_code==201,created.text
    assert created.json()['status']=='DRAFT'
    assert created.json()['input_method']=='TEXT'
    assert created.json()['approved_summary'] is None
    assert client.get('/api/v1/meetings').json()['items'][0]['id']==created.json()['id']
    supervisor=sign_in(client,'supervisor@advicue.local')['csrf_token']
    assert client.post('/api/v1/meetings/notes',json=payload,headers=auth(supervisor)).status_code==403


def test_meeting_approval_immutable_scoped_and_audited(client):
    csrf=sign_in(client)['csrf_token']
    item=client.post('/api/v1/meetings/notes',json={'investor_id':'A-001','transcript':'Follow up on approved goal targets and liquidity requirements.'},headers=auth(csrf)).json()
    assert client.post(f"/api/v1/meetings/{item['id']}/approve",json={'summary':'too short','commitments':[]},headers=auth(csrf)).status_code==422
    approved=client.post(f"/api/v1/meetings/{item['id']}/approve",json={'summary':'Discussed liquidity and requested updated investment-horizon information.','commitments':['Advisor to request an updated mandate.']},headers=auth(csrf))
    assert approved.status_code==200
    assert approved.json()['status']=='APPROVED'
    assert client.post(f"/api/v1/meetings/{item['id']}/approve",json={'summary':'Try to overwrite the approved meeting note text','commitments':[]},headers=auth(csrf)).status_code==409
    assert client.post(f"/api/v1/meetings/{item['id']}/extract",headers=auth(csrf)).status_code==409
    assert any(e['action']=='MEETING_NOTE_APPROVED' for e in client.get('/api/v1/audit-events').json()['items'])
    other=sign_in(client,'b@advicue.local')
    assert client.get(f"/api/v1/meetings/{item['id']}").status_code==404
    assert all(e['action'] != 'MEETING_NOTE_APPROVED' for e in client.get('/api/v1/audit-events').json()['items'])
    assert client.get(f"/api/v1/ai/briefs/A-001").status_code==404


def test_audio_consent_size_header_and_unsupported_file(client):
    csrf=sign_in(client)['csrf_token']
    endpoint='/api/v1/meetings/transcribe'
    def upload(consent, content=b'RIFF' + b'0'*200, name='session.wav'):
        return client.post(endpoint, data={'investor_id':'A-001','recording_consent':str(consent).lower()},
                           files={'audio':(name,content,'audio/wav')},headers=auth(csrf))
    assert upload(False).status_code==422
    assert upload(True,name='session.txt').status_code==415
    assert upload(True,b'fakeaudio').status_code==415
    assert client.get('/api/v1/meetings').json()['items']==[]


def test_audio_transcription_local_mock_and_consent(client):
    csrf=sign_in(client)['csrf_token']
    with patch('app.api.local_ai.transcribe_audio_locally',return_value='We discussed allocation and will verify client mandate.') as mock_asr:
        response=client.post('/api/v1/meetings/transcribe',data={'investor_id':'A-001','recording_consent':'true'},
          files={'audio':('recording.wav',b'RIFF' + b'0'*200,'audio/wav')},headers=auth(csrf))
    assert response.status_code==201,response.text
    assert response.json()['recording_consent'] is True
    assert response.json()['audio_sha256']
    mock_asr.assert_called_once()


def test_local_model_configuration_must_be_loopback(client):
    assert local_llama_cpp_url().startswith('http://')
    with patch('app.ai.local_models.settings', replace(settings, llama_cpp_url='https://api.example.com')):
        try: local_llama_cpp_url(); assert False
        except LocalModelError: pass
    with patch('app.ai.local_models.settings', replace(settings, llama_cpp_url='http://192.168.1.20:11434')):
        try: local_llama_cpp_url(); assert False
        except LocalModelError: pass


def seed_holding():
    with SessionLocal() as db:
        batch=ImportBatch(organization_id='org-a',filename='example.xlsx',file_sha256='a'*64,
            status='COMMITTED',uploaded_by='supervisor-a',total_rows=1,sheet_counts={'holdings':1})
        db.add(batch);db.flush()
        src=SourceRow(batch_id=batch.id,sheet_name='holdings',row_number=2,
                      raw_data={'investor_id':'A-001'},normalized_data={'investor_id':'A-001'})
        db.add(src);db.flush()
        db.add(Holding(organization_id='org-a',investor_id='A-001',source_row_id=src.id,
                       external_holding_id='H-A',as_of_date=date(2026,7,31),asset_class='Fixed Deposit',
                       instrument_name='Deposit',current_value=Decimal('25000.00')))
        db.commit();return src.id


def test_ai_brief_requires_real_evidence_and_rejects_hallucinated_references(client):
    csrf=sign_in(client)['csrf_token']
    endpoint='/api/v1/ai/briefs'
    assert client.post(endpoint,json={'investor_id':'A-001'},headers=auth(csrf)).status_code==422
    evidence=seed_holding()
    bad={'summary':'This is an allocation observation pending an advisor mandate review.',
         'review_questions':['Can the mandate be confirmed?'],'cited_fact_ids':['made-up-source']}
    with patch('app.api.local_ai.local_llm_json',return_value=bad):
        response=client.post(endpoint,json={'investor_id':'A-001'},headers=auth(csrf))
    assert response.status_code==422
    good={**bad,'cited_fact_ids':[evidence]}
    with patch('app.api.local_ai.local_llm_json',return_value=good):
        response=client.post(endpoint,json={'investor_id':'A-001'},headers=auth(csrf))
    assert response.status_code==201,response.text
    assert response.json()['cited_fact_ids']==[evidence]
    assert client.get('/api/v1/ai/briefs/A-001').json()['items'][0]['id']==response.json()['id']
    with patch('app.api.local_ai.local_llm_json',return_value={**good,'summary':'Lost 25% returns and needs an immediate trade.'}):
        assert client.post(endpoint,json={'investor_id':'A-001'},headers=auth(csrf)).status_code==422


def test_extraction_never_approves_automatically(client):
    csrf=sign_in(client)['csrf_token']
    item=client.post('/api/v1/meetings/notes',json={'investor_id':'A-001','transcript':'Advisor will confirm the investor mandate next week.'},headers=auth(csrf)).json()
    result={'summary':'Advisor plans to request written confirmation of mandate.','commitments':['Advisor to confirm mandate.'],'review_questions':['What is the agreed risk exposure?']}
    with patch('app.api.local_ai.local_llm_json',return_value=result):
        response=client.post(f"/api/v1/meetings/{item['id']}/extract",headers=auth(csrf))
    assert response.status_code==200,response.text
    assert response.json()['status']=='DRAFT'
    assert response.json()['extracted_draft']['commitments']==['Advisor to confirm mandate.']
    assert response.json()['approved_summary'] is None


def test_security_response_headers_and_audit_scope(client):
    response=client.get('/api/v1/health')
    assert response.headers['x-content-type-options']=='nosniff'
    assert response.headers['x-frame-options']=='DENY'
    assert response.headers['cache-control']=='no-store'
    sign_in(client,'supervisor@advicue.local')
    assert client.get('/api/v1/audit-events').json()['scope']=='ORGANIZATION'


def test_approved_meeting_links_to_same_investor_advice_only(client):
    """Cross-investor meeting-note references cannot be used to justify advice."""
    from app.models import AttentionCase, DetectedPattern, PatternRun
    csrf=sign_in(client)['csrf_token']
    note=client.post('/api/v1/meetings/notes',json={'investor_id':'A-001','transcript':'Advisor will verify an approved investment mandate.'},headers=auth(csrf)).json()
    with SessionLocal() as db:
        scan=PatternRun(organization_id='org-a',actor_id='supervisor-a',rule_version='v1',matched_count=1)
        db.add(scan);db.flush()
        pat=DetectedPattern(run_id=scan.id,organization_id='org-a',rule_id='TEST',rule_version='v1',snapshot_date=date(2026,7,31),member_count=1,advisor_count=1,recorded_value_total=Decimal('1000'),evidence_summary='Test evidence')
        db.add(pat);db.flush()
        case=AttentionCase(organization_id='org-a',investor_id='A-001',advisor_id='advisor-a',pattern_id=pat.id,rule_id='TEST',rule_version='v1',source_date=date(2026,7,31),priority='P2',status='OPEN',title='Test review',reason='Dated allocation requires review',suggested_action='Confirm client mandate',evidence_source_row_ids=[])
        db.add(case);db.commit();case_id=case.id
    payload={'alert_id':case_id,'recommendation':'Contact investor to confirm mandate.','rationale':'Investment records require client verification.','source_meeting_id':note['id']}
    assert client.post('/api/v1/advice',json=payload,headers=auth(csrf)).status_code==422
    assert client.post(f"/api/v1/meetings/{note['id']}/approve",json={'summary':'The advisor agreed to verify the investment mandate.','commitments':[]},headers=auth(csrf)).status_code==200
    result=client.post('/api/v1/advice',json=payload,headers=auth(csrf))
    assert result.status_code==201,result.text
    assert result.json()['source_meeting_id']==note['id']


def test_discard_unapproved_transcript_and_keep_audit(client):
    csrf=sign_in(client)['csrf_token']
    note=client.post('/api/v1/meetings/notes',json={'investor_id':'A-001','transcript':'I recorded notes that should now be discarded.'},headers=auth(csrf)).json()
    response=client.post(f"/api/v1/meetings/{note['id']}/discard",headers=auth(csrf))
    assert response.status_code==200
    assert client.get(f"/api/v1/meetings/{note['id']}").status_code==404
    assert any(x['action']=='MEETING_DRAFT_DISCARDED' for x in client.get('/api/v1/audit-events').json()['items'])
