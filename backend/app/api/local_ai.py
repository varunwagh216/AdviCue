"""Phases 7 and 8: local-only grounded AI and human-approved meeting notes.

All client reads are scoped to an organization and assigned advisor; model output
never authorizes investment advice, creates tasks or trades without human action.
"""
from __future__ import annotations
from datetime import datetime, timezone, date
from hashlib import sha256
import json
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.ai.local_models import LocalModelError, local_llm_json, transcribe_audio_locally, local_llama_cpp_url
from app.ai.fact_templates import render_fact_template,UnverifiedNumericClaim
from app.api.intelligence import investor_scope, analysis
from app.api.workflow import _log
from app.core.config import settings
from app.core.database import get_db
from app.core.security import current_user, csrf_protected, require_same_origin
from app.models import LocalAIBrief, MeetingNote, User, Investor, Holding, CommitmentCheck

router = APIRouter(tags=['Local AI & Meetings'])


def fail_local(exc: LocalModelError) -> HTTPException:
    return HTTPException(status_code=503, detail=str(exc))


def _meeting(db: Session, user: User, note_id: str) -> MeetingNote:
    q = select(MeetingNote).where(MeetingNote.id == note_id, MeetingNote.organization_id == user.organization_id)
    if user.role == 'ADVISOR':
        q = q.where(MeetingNote.advisor_id == user.id)
    row = db.scalar(q)
    if not row:
        raise HTTPException(status_code=404, detail='Meeting note not found')
    investor_scope(db, user, row.investor_id)
    return row


def meeting_out(row: MeetingNote) -> dict:
    return {'id': row.id, 'investor_id': row.investor_id, 'status': row.status,
            'input_method': row.input_method, 'transcript': row.transcript,
            'recording_consent': row.recording_consent_at is not None,
            'audio_sha256': row.audio_sha256,
            'extracted_draft': row.extracted_draft,
            'approved_summary': row.approved_summary,
            'approved_commitments': row.approved_commitments,
            'approved_preferences':row.approved_preferences,
            'created_at': row.created_at.isoformat(),
            'approved_at': row.approved_at.isoformat() if row.approved_at else None,
            'approved_by': row.approved_by,
            'note': 'No advice, trading order or follow-up task is created automatically.'}


def _require_advisor(user: User):
    if user.role != 'ADVISOR':
        raise HTTPException(status_code=403, detail='Only assigned advisors can create or approve meeting notes')


@router.get('/ai/status')
def ai_status(user: User = Depends(current_user)):
    """Only configuration state; does not trigger model loading or download."""
    try:
        local_llama_cpp_url()
        configured = True
    except LocalModelError:
        configured = False
    from app.ai.speech import speech_assets
    exe,model=speech_assets()
    return {'llama_cpp_local_config_valid': configured, 'provider': 'llama.cpp', 'model': settings.llama_cpp_model,
            'transcription_provider':'whisper.cpp','transcription_assets_present':exe.is_file() and model.is_file(),
            'transcription_model': model.name,
            'note': 'Configured does not mean the local model is installed or currently available.'}


class BriefInput(BaseModel):
    investor_id: str = Field(min_length=1, max_length=40)


@router.post('/ai/briefs', status_code=201)
def create_brief(payload: BriefInput, request: Request, user: User = Depends(csrf_protected),
                 db: Session = Depends(get_db)):
    require_same_origin(request)
    inv = investor_scope(db, user, payload.investor_id)
    data = analysis(inv.id, user=user, db=db)
    allocation = data['allocation']
    # Facts must come from validated deterministic modules. Never pass unrelated clients.
    facts = {
        'investor_id': inv.id,
        'risk_profile': inv.risk_profile,
        'allocation_as_of_date': allocation.get('as_of_date'),
        'asset_allocation': [{k: item.get(k) for k in ('asset_class','value','weight_pct')} for item in allocation.get('asset_classes', [])],
        'equity_pct': allocation.get('equity_pct'),
        'fixed_deposit_pct': allocation.get('fixed_deposit_pct'),
        'reviewed_performance':data.get('reviewed_performance'),
        'performance_status': data['performance']['status'],
        'performance_reason': data['performance']['reason'],
        'goal_status': data['goal']['status'],
        'goal_target_amount':data['goal']['target_amount'],
        'goal_target_date':data['goal']['target_date'],
        'reported_comparison':{k:v for k,v in data['reported_comparison'].items() if k!='months'},
        'peer_allocation_explanation':data['peer_exposure']['note'],
        'advisor_approved_preferences':inv.advisor_preferences,
        'observed_behaviour_signals':[{k:v for k,v in signal.items() if k not in ('source_row_ids',)} for signal in data['behaviour_signals']],
        'risk_assessment': data['assessment'],
    }
    evidence_ids = list(dict.fromkeys(allocation.get('source_row_ids', [])+data['reported_comparison'].get('source_row_ids', [])))
    if not evidence_ids:
        raise HTTPException(status_code=422, detail='No validated dated holding source rows available to cite')
    facts['available_evidence_ids'] = evidence_ids[:100]
    system = ("You are a cautious FINANCIAL REVIEW NOTE drafting assistant. Use only supplied facts. "
              "Never invent a return, benchmark, suitability finding, cash-flow or action. "
              "Do not claim an allocation is wrong or suggest a trade. "
              "Return JSON with summary (<=900 chars), review_questions (1-4 short strings), "
              "cited_fact_ids (1-15 strings copied EXACTLY from available_evidence_ids). "
              "Use bracketed placeholders like [[EQUITY_PCT]], [[FD_PCT]], [[SUM_GAP_PP]], [[GOAL_AMOUNT]] or [[GOAL_DATE]] for numerical facts. "
              "Never write bare numbers, percentages, currency amounts or dates. State uncertainties clearly. "
              "Keep summary to two short sentences and ask at most two review questions. Do not repeat the input JSON.")
    try:
        schema={'type':'object','additionalProperties':False,'required':['summary','review_questions','cited_fact_ids'],'properties':{
            'summary':{'type':'string','pattern':r'^[^0-9₹$"\\\n\r\t]{15,300}$'},
            'review_questions':{'type':'array','minItems':1,'maxItems':2,'items':{'type':'string','pattern':r'^[^0-9₹$"\\\n\r\t]{4,120}$'}},
            'cited_fact_ids':{'type':'array','minItems':1,'maxItems':5,'items':{'type':'string','enum':evidence_ids[:100]}}}}
        # Give the small local model a compact drafting context. Quantities are
        # backend-owned placeholders; the complete source facts remain in the audit snapshot.
        model_facts={'risk_profile':inv.risk_profile,'asset_categories':[x['asset_class'] for x in facts['asset_allocation']],
            'performance_status':facts['performance_status'],'performance_uncertainty':facts['performance_reason'],
            'goal_status':facts['goal_status'],'approved_preferences':facts['advisor_approved_preferences'],
            'quantitative_facts':{key:'[['+key+']]' for key,value in {'EQUITY_PCT':facts['equity_pct'],'FD_PCT':facts['fixed_deposit_pct'],'GOAL_AMOUNT':facts['goal_target_amount'],'GOAL_DATE':facts['goal_target_date']}.items() if value is not None},
            'available_evidence_ids':facts['available_evidence_ids']}
        result = local_llm_json(system, model_facts,response_schema=schema)
    except LocalModelError as exc:
        raise fail_local(exc) from exc
    summary = result.get('summary')
    questions = result.get('review_questions')
    citations = result.get('cited_fact_ids')
    if (not isinstance(summary, str) or not 15 <= len(summary.strip()) <= 900
            or not isinstance(questions, list) or not 1 <= len(questions) <= 4
            or not all(isinstance(q, str) and 4 <= len(q.strip()) <= 240 for q in questions)
            or not isinstance(citations, list) or not 1 <= len(citations) <= 15
            or not all(isinstance(c, str) and c in evidence_ids for c in citations)):
        raise HTTPException(status_code=422, detail='Local AI reply failed provenance validation; no brief was saved')
    # Only deterministic backend substitutions may produce quantitative statements,
    # including in questions. Local-model prose cannot invent dates or amounts.
    allowed={
        'EQUITY_PCT':allocation.get('equity_pct'),
        'FD_PCT':allocation.get('fixed_deposit_pct'),
        'SUM_GAP_PP':data['reported_comparison'].get('sum_monthly_gap_pp'),
        'GOAL_AMOUNT':data['goal'].get('target_amount'),
        'GOAL_DATE':data['goal'].get('target_date'),
    }
    try:
        summary=render_fact_template(summary.strip(),allowed)
        questions=[render_fact_template(q.strip(),allowed) for q in questions]
    except UnverifiedNumericClaim as exc:
        raise HTTPException(status_code=422,detail=f'Local AI brief rejected: {exc}') from exc
    row = LocalAIBrief(organization_id=user.organization_id, investor_id=inv.id,
                       created_by=user.id, model_name=settings.llama_cpp_model,
                       summary=summary.strip(), review_questions=[q.strip() for q in questions],
                       cited_fact_ids=list(dict.fromkeys(citations)), fact_snapshot=facts)
    db.add(row); db.flush()
    _log(db, user, 'LOCAL_AI_BRIEF_CREATED', 'LocalAIBrief', row.id,
         {'investor_id': inv.id, 'citations': row.cited_fact_ids})
    db.commit()
    return {'id': row.id, 'investor_id': inv.id, 'summary': row.summary,
            'review_questions': row.review_questions, 'cited_fact_ids': row.cited_fact_ids,
            'facts': facts, 'model': row.model_name,
            'disclaimer': 'Draft explanation only. Advisor must review source evidence; no automatic financial advice.'}


@router.get('/ai/briefs/{investor_id}')
def list_briefs(investor_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    investor_scope(db, user, investor_id)
    rows = db.scalars(select(LocalAIBrief).where(LocalAIBrief.organization_id == user.organization_id,
                      LocalAIBrief.investor_id == investor_id).order_by(LocalAIBrief.created_at.desc()).limit(20)).all()
    return {'items': [{'id': r.id, 'investor_id': r.investor_id, 'summary': r.summary,
                       'review_questions': r.review_questions, 'cited_fact_ids': r.cited_fact_ids,
                       'model': r.model_name, 'created_at': r.created_at.isoformat()} for r in rows]}


class TextNoteInput(BaseModel):
    investor_id: str = Field(min_length=1, max_length=40)
    transcript: str = Field(min_length=12, max_length=30000)


@router.post('/meetings/notes', status_code=201)
def create_typed_note(payload: TextNoteInput, request: Request,
                      user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    require_same_origin(request)
    _require_advisor(user)
    investor_scope(db, user, payload.investor_id)
    row = MeetingNote(organization_id=user.organization_id, investor_id=payload.investor_id,
                      advisor_id=user.id, input_method='TEXT', transcript=payload.transcript.strip())
    db.add(row); db.flush()
    _log(db, user, 'MEETING_DRAFT_CREATED', 'MeetingNote', row.id, {'input': 'TEXT'})
    db.commit()
    return meeting_out(row)


_AUDIO_FORMATS = {'.wav': b'RIFF', '.mp3': b'ID3', '.ogg': b'OggS', '.webm': b'\x1a\x45\xdf\xa3', '.m4a': b''}


@router.post('/meetings/transcribe', status_code=201)
async def upload_meeting_audio(request: Request,
                               investor_id: str = Form(...), recording_consent: bool = Form(False),
                               audio: UploadFile = File(...), user: User = Depends(csrf_protected),
                               db: Session = Depends(get_db)):
    require_same_origin(request)
    _require_advisor(user)
    investor_scope(db, user, investor_id)
    if not recording_consent:
        raise HTTPException(status_code=422, detail='Recording consent must be confirmed before local transcription')
    import pathlib
    suffix = pathlib.Path(audio.filename or '').suffix.lower()
    if suffix not in _AUDIO_FORMATS:
        raise HTTPException(status_code=415, detail='Use a WAV, MP3, M4A, OGG or WEBM recording')
    max_size = min(settings.max_audio_mb, 25) * 1024 * 1024
    payload = await audio.read(max_size + 1)
    await audio.close()
    if not payload or len(payload) > max_size:
        raise HTTPException(status_code=413, detail=f'Audio must be between 1 byte and {max_size} bytes')
    signature = _AUDIO_FORMATS[suffix]
    if signature and not payload.startswith(signature):
        if not (suffix == '.mp3' and payload[:1] == b'\xff'):
            raise HTTPException(status_code=415, detail='Audio contents do not match selected extension')
    if suffix == '.m4a' and b'ftyp' not in payload[:32]:
        raise HTTPException(status_code=415, detail='Invalid M4A header')
    try:
        from starlette.concurrency import run_in_threadpool
        text = await run_in_threadpool(transcribe_audio_locally, payload, suffix)
    except LocalModelError as exc:
        raise fail_local(exc) from exc
    row = MeetingNote(organization_id=user.organization_id, investor_id=investor_id,
                      advisor_id=user.id, input_method='LOCAL_AUDIO',
                      recording_consent_at=datetime.now(timezone.utc), audio_sha256=sha256(payload).hexdigest(),
                      transcript=text)
    db.add(row); db.flush()
    _log(db, user, 'MEETING_DRAFT_CREATED', 'MeetingNote', row.id, {'input': 'LOCAL_AUDIO', 'consent': True})
    db.commit()
    return meeting_out(row)


@router.get('/meetings')
def list_meetings(investor_id: str | None = None, user: User = Depends(current_user), db: Session = Depends(get_db)):
    q = select(MeetingNote).where(MeetingNote.organization_id == user.organization_id)
    if investor_id:
        investor_scope(db, user, investor_id)
        q = q.where(MeetingNote.investor_id == investor_id)
    if user.role == 'ADVISOR':
        q = q.where(MeetingNote.advisor_id == user.id)
    rows = db.scalars(q.order_by(MeetingNote.created_at.desc()).limit(100)).all()
    return {'items': [meeting_out(r) for r in rows]}


@router.get('/meetings/{note_id}')
def get_meeting(note_id: str, user: User = Depends(current_user), db: Session = Depends(get_db)):
    return meeting_out(_meeting(db, user, note_id))


@router.post('/meetings/{note_id}/extract')
def extract_meeting(note_id: str, request: Request, user: User = Depends(csrf_protected),
                    db: Session = Depends(get_db)):
    require_same_origin(request)
    _require_advisor(user)
    row = _meeting(db, user, note_id)
    if row.status != 'DRAFT':
        raise HTTPException(status_code=409, detail='Approved notes are immutable')
    system = ('Extract DRAFT meeting notes only from the supplied transcript. Return JSON with '
              'summary (short string), commitments (0-6 strings; only if explicitly mentioned), '
              'review_questions (0-5 strings), preferences (object: liquidity_needs, risk_concerns, life_events; use null unless explicitly stated). Do NOT invent advice, commitments or client goals. '
              'Include every explicit future action assigned to the advisor or client as a commitment, including a promised review or document request. '
              'Copy the action sentence from the transcript and retain its timing. A commitment is an action, not a promise of investment returns. '
              'Example: if the transcript says "The advisor will request the statement on Monday", commitments contains that exact sentence. '
              'Do not copy the example unless it is in the transcript. The advisor must review and approve before any record becomes official.')
    # Process the entire note in bounded overlapping chunks; never save a partial extraction.
    chunks=[]
    start=0
    while start<len(row.transcript):
        end=min(start+6000,len(row.transcript))
        chunks.append(row.transcript[start:end])
        if end==len(row.transcript):break
        start=end-300
    summaries=[];commitments=[];questions=[];prefs={}
    for index,chunk in enumerate(chunks):
        try:
            strings=lambda n:{'type':'array','maxItems':n,'items':{'type':'string','minLength':1,'maxLength':220}}
            schema={'type':'object','additionalProperties':False,'required':['summary','commitments','review_questions','preferences'],'properties':{
                'summary':{'type':'string','minLength':5,'maxLength':500},'commitments':strings(6),'review_questions':strings(5),
                'preferences':{'type':'object','additionalProperties':False,'properties':{k:{'type':['string','null'],'maxLength':180} for k in ('liquidity_needs','risk_concerns','life_events')}}}}
            result=local_llm_json(system,{'transcript':chunk,'chunk':index+1,'total_chunks':len(chunks)},response_schema=schema)
        except LocalModelError as exc:
            raise fail_local(exc) from exc
        summary=result.get('summary');proposed=result.get('commitments');review=result.get('review_questions')
        if (not isinstance(summary,str) or not 5<=len(summary.strip())<=2000
            or not isinstance(proposed,list) or len(proposed)>6
            or not isinstance(review,list) or len(review)>5
            or not all(isinstance(v,str) and 1<=len(v.strip())<=400 for v in proposed+review)):
            raise HTTPException(status_code=422,detail=f'Invalid extraction in section {index+1}; no partial draft was saved')
        summaries.append(summary.strip())
        commitments.extend(v.strip() for v in proposed if v.strip() not in commitments)
        questions.extend(v.strip() for v in review if v.strip() not in questions)
        extracted=result.get('preferences',{})
        if isinstance(extracted,dict):
            for key in ('liquidity_needs','risk_concerns','life_events'):
                value=extracted.get(key)
                if isinstance(value,str) and 1<=len(value.strip())<=300:
                    old=prefs.get(key,'')
                    if value.strip() not in old:prefs[key]=(old+'; '+value.strip()).strip('; ')
    summary=' '.join(summaries)
    if len(summary)>2000 or len(commitments)>30 or len(questions)>30 or any(len(v)>300 for v in prefs.values()):
        raise HTTPException(status_code=422,detail='Complete extraction exceeds review limits. Split the meeting into shorter notes; no content was silently dropped.')
    row.extracted_draft={'summary':summary,'commitments':commitments,'review_questions':questions,'preferences':prefs,
        'coverage':{'characters_processed':len(row.transcript),'total_characters':len(row.transcript),'chunks':len(chunks),'complete':True}}
    _log(db, user, 'MEETING_DRAFT_EXTRACTED', 'MeetingNote', row.id)
    db.commit()
    return meeting_out(row)


class ApproveNoteInput(BaseModel):
    summary: str = Field(min_length=12, max_length=2000)
    commitments: list[str] = Field(default_factory=list, max_length=30)
    preferences:dict[str,str]=Field(default_factory=dict)


@router.post('/meetings/{note_id}/approve')
def approve_meeting(note_id: str, payload: ApproveNoteInput, request: Request,
                    user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    require_same_origin(request)
    _require_advisor(user)
    row = _meeting(db, user, note_id)
    if row.status != 'DRAFT':
        raise HTTPException(status_code=409, detail='Note is already approved; approved records cannot be modified')
    if any(not 2 <= len(v.strip()) <= 400 for v in payload.commitments):
        raise HTTPException(status_code=422, detail='Commitments must be 2â€“400 characters long')
    row.approved_summary = payload.summary.strip()
    row.approved_commitments = [x.strip() for x in payload.commitments]
    allowed_preferences={'liquidity_needs','risk_concerns','life_events'}
    if (set(payload.preferences)-allowed_preferences or any(not 1<=len(v.strip())<=300 for v in payload.preferences.values())):
        raise HTTPException(status_code=422,detail='Preferences must use approved fields and 1â€“300 characters')
    row.approved_preferences={k:v.strip() for k,v in payload.preferences.items()}
    inv=investor_scope(db,user,row.investor_id)
    if row.approved_preferences:
        inv.advisor_preferences={'values':row.approved_preferences,'approved_note_id':row.id,
                                 'recorded_at':datetime.now(timezone.utc).isoformat()}
    row.approved_at = datetime.now(timezone.utc)
    row.approved_by = user.id
    row.status = 'APPROVED'
    _log(db, user, 'MEETING_NOTE_APPROVED', 'MeetingNote', row.id,
         {'investor_id': row.investor_id, 'commitments_count': len(row.approved_commitments)})
    db.commit()
    return meeting_out(row)



@router.post('/meetings/{note_id}/discard')
def discard_meeting_draft(note_id: str, request: Request,
                          user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    """Delete an unapproved transcript/draft. Retain a content-free audit record."""
    require_same_origin(request)
    _require_advisor(user)
    row = _meeting(db, user, note_id)
    if row.status != 'DRAFT':
        raise HTTPException(status_code=409, detail='Approved notes must follow the documented records-retention process')
    _log(db, user, 'MEETING_DRAFT_DISCARDED', 'MeetingNote', row.id, {'investor_id': row.investor_id})
    db.delete(row)
    db.commit()
    return {'deleted': True, 'id': note_id, 'audit_retained': True}


class CheckableCommitment(BaseModel):
    metric:Literal['equity_pct','fixed_deposit_pct']
    comparator:Literal['>=','<=']
    target_pct:float=Field(ge=0,le=100)
    due_date:date

@router.post('/meetings/{note_id}/commitment-checks',status_code=201)
def create_commitment_check(note_id:str,payload:CheckableCommitment,request:Request,
      user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    _require_advisor(user)
    note=_meeting(db,user,note_id)
    if note.status!='APPROVED' or not note.approved_commitments:
        raise HTTPException(status_code=422,detail='Advisor-approved meeting with documented commitments required')
    if payload.due_date < note.approved_at.date():
        raise HTTPException(status_code=422,detail='Commitment due date cannot be before the meeting approval')
    from decimal import Decimal
    item=CommitmentCheck(organization_id=user.organization_id,investor_id=note.investor_id,
         advisor_id=user.id,meeting_id=note.id,metric=payload.metric,comparator=payload.comparator,
         target_pct=Decimal(str(payload.target_pct)),due_date=payload.due_date)
    db.add(item);db.flush()
    _log(db,user,'CHECKABLE_COMMITMENT_CREATED','CommitmentCheck',item.id,
         {'note_id':note.id,'metric':payload.metric,'comparator':payload.comparator,'due_date':payload.due_date.isoformat()})
    db.commit()
    return {'id':item.id,'investor_id':note.investor_id,'status':'NOT_ASSESSABLE',
            'reason':'No post-commitment holdings reviewed yet; promise is not automatically kept.'}

@router.get('/investors/{investor_id}/commitment-checks')
def list_commitment_checks(investor_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from app.engines.advanced import check_commitment_against_dated_holdings
    investor_scope(db,user,investor_id)
    query=select(CommitmentCheck).where(CommitmentCheck.organization_id==user.organization_id,
                                        CommitmentCheck.investor_id==investor_id)
    if user.role=='ADVISOR':query=query.where(CommitmentCheck.advisor_id==user.id)
    checks=db.scalars(query).all()
    holdings=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id,
                                              Holding.investor_id==investor_id)).all()
    rows=[]
    for check in checks:
        note=_meeting(db,user,check.meeting_id)
        evaluation=check_commitment_against_dated_holdings(check,note,holdings)
        rows.append({'id':check.id,'meeting_id':check.meeting_id,'metric':check.metric,
                     'comparator':check.comparator,'target_pct':str(check.target_pct),
                     'due_date':check.due_date.isoformat(),
                     'illustrative_demo_only':note.transcript.startswith(('ILLUSTRATIVE SIMULATED COMMITMENT','Sample commitment record.')),
                     **evaluation})
    return {'items':rows}
