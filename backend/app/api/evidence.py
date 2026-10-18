"""Scoped source review, benchmark policies, pilot measurements and client timelines."""
from datetime import date, datetime, timezone
from decimal import Decimal
from hashlib import sha256
import json
from statistics import median
from typing import Literal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import current_user, csrf_protected, require_same_origin
from app.models import User, Investor, ReviewEvidence, PilotSession, AuditEvent, AttentionCase, AdviceRecord, FollowUpTask, MeetingNote, Holding
from app.engines.evidence import PerformanceEvidence, MandateEvidence, reconcile, validate_mandate
from app.core.clock import utc_iso,advisor_day

router=APIRouter(tags=['Evidence and review measurement'])


def scope(db,user,iid):
    q=select(Investor).where(Investor.id==iid,Investor.organization_id==user.organization_id)
    if user.role=='ADVISOR':q=q.where(Investor.advisor_id==user.id)
    inv=db.scalar(q)
    if not inv:raise HTTPException(status_code=404,detail='Client not found')
    return inv


def latest(db,user,iid,kind):
    return db.scalar(select(ReviewEvidence).where(ReviewEvidence.organization_id==user.organization_id,ReviewEvidence.investor_id==iid,
        ReviewEvidence.kind==kind,ReviewEvidence.status=='APPROVED').order_by(ReviewEvidence.approved_at.desc(),ReviewEvidence.id.desc()))


def public(row):
    return {'id':row.id,'kind':row.kind,'status':row.status,'payload':row.payload,'sha256':row.payload_sha256,
        'created_at':row.created_at.isoformat(),'approved_at':row.approved_at.isoformat() if row.approved_at else None,'approval_note':row.approval_note}


def save(db,user,iid,kind,payload):
    encoded=json.dumps(payload,sort_keys=True,separators=(',',':'))
    if len(encoded)>2*1024*1024:raise HTTPException(status_code=413,detail='Evidence manifest exceeds 2 MB')
    digest=sha256(encoded.encode()).hexdigest()
    row=db.scalar(select(ReviewEvidence).where(ReviewEvidence.organization_id==user.organization_id,ReviewEvidence.investor_id==iid,ReviewEvidence.kind==kind,ReviewEvidence.payload_sha256==digest))
    if row:return public(row)
    row=ReviewEvidence(organization_id=user.organization_id,investor_id=iid,advisor_id=user.id,kind=kind,status='DRAFT',payload=payload,payload_sha256=digest)
    db.add(row);db.flush();db.add(AuditEvent(organization_id=user.organization_id,actor_id=user.id,action='EVIDENCE_STAGED',entity_type='ReviewEvidence',entity_id=row.id,detail=json.dumps({'kind':kind,'sha256':digest})))
    db.commit();return public(row)


@router.post('/investors/{iid}/performance-evidence',status_code=201)
def stage_performance(iid:str,payload:PerformanceEvidence,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request);scope(db,user,iid)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Assigned advisor required')
    if payload.client_id!=iid:raise HTTPException(status_code=422,detail='Evidence client ID does not match the selected client')
    try:calculated=reconcile(payload)
    except (ValueError,ArithmeticError) as exc:raise HTTPException(status_code=422,detail=str(exc))
    return {**save(db,user,iid,'PERFORMANCE',payload.model_dump(mode='json')),'calculation':calculated}


@router.post('/investors/{iid}/mandate',status_code=201)
def stage_mandate(iid:str,payload:MandateEvidence,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request);scope(db,user,iid)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Assigned advisor required')
    if payload.client_id!=iid:raise HTTPException(status_code=422,detail='Mandate client ID does not match the selected client')
    try:validate_mandate(payload)
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc))
    return save(db,user,iid,'MANDATE',payload.model_dump(mode='json'))


class Approval(BaseModel):
    source_review_completed:Literal[True]
    note:str=Field(min_length=20,max_length=2000)


@router.post('/investors/{iid}/evidence/{eid}/approve')
def approve(iid:str,eid:str,payload:Approval,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request);scope(db,user,iid)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Assigned advisor required')
    row=db.scalar(select(ReviewEvidence).where(ReviewEvidence.id==eid,ReviewEvidence.organization_id==user.organization_id,ReviewEvidence.investor_id==iid))
    if not row:raise HTTPException(status_code=404,detail='Evidence not found')
    if row.status!='DRAFT':raise HTTPException(status_code=409,detail='Approved evidence is immutable; stage a new revision')
    if len(payload.note.strip())<20:raise HTTPException(status_code=422,detail='Explain the source review in at least 20 characters')
    try:
        if row.kind=='PERFORMANCE':reconcile(PerformanceEvidence.model_validate(row.payload))
        else:validate_mandate(MandateEvidence.model_validate(row.payload))
    except ValueError as exc:raise HTTPException(status_code=422,detail=str(exc))
    row.status='APPROVED';row.approved_at=datetime.now(timezone.utc);row.approval_note=payload.note.strip()
    db.add(AuditEvent(organization_id=user.organization_id,actor_id=user.id,action='SOURCE_EVIDENCE_APPROVED',entity_type='ReviewEvidence',entity_id=row.id,detail=json.dumps({'sha256':row.payload_sha256,'source_review_completed':True})))
    db.commit();return public(row)


@router.get('/investors/{iid}/evidence')
def evidence_list(iid:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    scope(db,user,iid)
    rows=db.scalars(select(ReviewEvidence).where(ReviewEvidence.organization_id==user.organization_id,ReviewEvidence.investor_id==iid).order_by(ReviewEvidence.created_at.desc()).limit(30)).all()
    return {'items':[public(r) for r in rows]}


@router.get('/investors/{iid}/verified-analysis')
def verified_analysis(iid:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    scope(db,user,iid);row=latest(db,user,iid,'PERFORMANCE');mandate=latest(db,user,iid,'MANDATE')
    if not row:return {'status':'EVIDENCE_REQUIRED','reason':'Reviewed flow statements, valuation boundaries and client-appropriate benchmark policy are required.','mandate':public(mandate) if mandate else None}
    result=reconcile(PerformanceEvidence.model_validate(row.payload))
    result.update(status='ILLUSTRATIVE_RECONCILED' if row.payload.get('illustrative') else 'ADVISOR_REVIEWED_RECONCILED',evidence_id=row.id,evidence_sha256=row.payload_sha256,
        reviewed_at=row.approved_at.isoformat(),benchmark_policy=row.payload['benchmark_policy'],mandate=public(mandate) if mandate else None)
    return result


class StartPilot(BaseModel):
    investor_id:str
    case_id:str|None=None
    voluntary_return:bool|None=None


@router.post('/pilot/sessions',status_code=201)
def start_pilot(payload:StartPilot,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request);scope(db,user,payload.investor_id)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Assigned advisor required')
    if payload.case_id:
        case=db.scalar(select(AttentionCase).where(AttentionCase.id==payload.case_id,AttentionCase.organization_id==user.organization_id,AttentionCase.investor_id==payload.investor_id))
        if not case:raise HTTPException(status_code=404,detail='Review case not found')
    existing=db.scalar(select(PilotSession).where(PilotSession.advisor_id==user.id,PilotSession.organization_id==user.organization_id,PilotSession.finished_at.is_(None)))
    if existing:raise HTTPException(status_code=409,detail='Finish the current measured review before starting another')
    row=PilotSession(organization_id=user.organization_id,advisor_id=user.id,investor_id=payload.investor_id,case_id=payload.case_id,sampling_method='FLAGGED' if payload.case_id else 'CLIENT_REVIEW',voluntary_return=payload.voluntary_return)
    db.add(row);db.commit()
    return {'id':row.id,'started_at':utc_iso(row.started_at),'investor_id':row.investor_id,'case_id':row.case_id}


class FinishPilot(BaseModel):
    outcome:Literal['RELEVANT','FALSE_POSITIVE','NOT_ASSESSABLE']
    baseline_seconds:int|None=Field(default=None,ge=1,le=86400)
    already_known:bool|None=None
    discovery_note:str|None=Field(default=None,max_length=2000)
    missed_issue:bool|None=None
    voluntary_return:bool|None=None


@router.post('/pilot/sessions/{sid}/finish')
def finish_pilot(sid:str,payload:FinishPilot,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    row=db.scalar(select(PilotSession).where(PilotSession.id==sid,PilotSession.organization_id==user.organization_id,PilotSession.advisor_id==user.id))
    if not row:raise HTTPException(status_code=404,detail='Pilot session not found')
    scope(db,user,row.investor_id)
    if row.finished_at:raise HTTPException(status_code=409,detail='Session already completed')
    if row.sampling_method=='RANDOM_UNFLAGGED' and payload.outcome!='NOT_ASSESSABLE' and payload.missed_issue is None:raise HTTPException(status_code=422,detail='Record whether the random control review found a missed issue')
    if payload.outcome=='NOT_ASSESSABLE' and payload.missed_issue is not None:raise HTTPException(status_code=422,detail='An unassessable review cannot be labelled as a control pass or miss')
    if (payload.missed_issue or payload.already_known is False) and len((payload.discovery_note or '').strip())<12:
        raise HTTPException(status_code=422,detail='Describe the new discovery or missed issue in at least 12 characters')
    now=datetime.now(timezone.utc);start=row.started_at.replace(tzinfo=timezone.utc) if row.started_at.tzinfo is None else row.started_at
    elapsed=max(0,int((now-start).total_seconds()))
    if elapsed>86400 and (payload.baseline_seconds or payload.outcome!='NOT_ASSESSABLE'):
        raise HTTPException(status_code=422,detail='Review exceeded 24 hours; finish as not assessable without a baseline')
    row.finished_at=now;row.elapsed_seconds=elapsed;row.outcome=payload.outcome;row.baseline_seconds=payload.baseline_seconds
    row.already_known=payload.already_known;row.discovery_note=payload.discovery_note;row.missed_issue=payload.missed_issue
    if payload.voluntary_return is not None:row.voluntary_return=payload.voluntary_return
    db.add(AuditEvent(organization_id=user.organization_id,actor_id=user.id,action='PILOT_REVIEW_COMPLETED',entity_type='PilotSession',entity_id=row.id,detail=json.dumps({'outcome':row.outcome,'elapsed_seconds':elapsed})))
    db.commit();return {'id':row.id,'elapsed_seconds':elapsed,'outcome':row.outcome}


@router.get('/pilot/summary')
def pilot_summary(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(select(PilotSession).where(PilotSession.organization_id==user.organization_id,PilotSession.advisor_id==user.id)).all()
    allowed={i.id for i in db.scalars(select(Investor).where(Investor.organization_id==user.organization_id,Investor.advisor_id==user.id)).all()}
    rows=[r for r in rows if r.investor_id in allowed];complete=[r for r in rows if r.finished_at]
    timed=[r for r in complete if r.elapsed_seconds is not None and r.elapsed_seconds<=86400]
    labelled=[r for r in complete if r.case_id and r.outcome in ('RELEVANT','FALSE_POSITIVE')]
    paired=[r for r in timed if r.baseline_seconds]
    dates={advisor_day(r.started_at).isoformat() for r in rows}
    active=next((r for r in rows if not r.finished_at),None)
    latest_labels={}
    for row in sorted(labelled,key=lambda r:(r.finished_at,r.id)):latest_labels[row.case_id]=row
    controls=[r for r in complete if r.sampling_method=='RANDOM_UNFLAGGED' and r.missed_issue is not None]
    discovery=[r for r in latest_labels.values() if r.outcome=='RELEVANT' and r.already_known is False and r.discovery_note]
    voluntary_dates={advisor_day(r.started_at).isoformat() for r in complete if r.voluntary_return is True}
    voluntary_dates.discard(min(dates) if dates else '')
    return {'sessions_started':len(rows),'reviews_completed':len(complete),'active_days':len(dates),'repeat_usage_days':max(0,len(dates)-1),
        'useful_new_discoveries':len(discovery),'unique_labelled_cases':len(latest_labels),
        'unique_case_false_positive_rate':sum(r.outcome=='FALSE_POSITIVE' for r in latest_labels.values())/len(latest_labels) if latest_labels else None,
        'random_controls_assessed':len(controls),'random_controls_with_missed_issues':sum(r.missed_issue is True for r in controls),
        'random_control_miss_rate':sum(r.missed_issue is True for r in controls)/len(controls) if controls else None,
        'voluntary_return_days':len(voluntary_dates),'voluntary_responses':sum(r.voluntary_return is not None for r in complete),
        'median_elapsed_seconds':median([r.elapsed_seconds for r in timed]) if timed else None,
        'labelled_case_reviews':len(labelled),'false_positive_rate':sum(r.outcome=='FALSE_POSITIVE' for r in labelled)/len(labelled) if labelled else None,
        'paired_baseline_count':len(paired),'median_reported_time_difference_seconds':median([r.baseline_seconds-r.elapsed_seconds for r in paired]) if paired else None,
        'active_session':{'id':active.id,'investor_id':active.investor_id,'investor_name':db.get(Investor,active.investor_id).display_name,'case_id':active.case_id,'sampling_method':active.sampling_method,'started_at':utc_iso(active.started_at)} if active else None,
        'note':'Pilot instrumentation, not a completed study. Elapsed wall time includes idle time. Baselines are advisor-entered; false-positive labels are human judgments. Repeat days do not prove retention.'}


@router.post('/pilot/random-control',status_code=201)
def random_control(request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Assigned advisor required')
    if db.scalar(select(PilotSession).where(PilotSession.organization_id==user.organization_id,PilotSession.advisor_id==user.id,PilotSession.finished_at.is_(None))):raise HTTPException(status_code=409,detail='Finish the current measured review first')
    clients=db.scalars(select(Investor).where(Investor.organization_id==user.organization_id,Investor.advisor_id==user.id)).all()
    flagged=set(db.scalars(select(AttentionCase.investor_id).where(AttentionCase.organization_id==user.organization_id,AttentionCase.investor_id.in_([i.id for i in clients]),AttentionCase.status!='RESOLVED',AttentionCase.superseded_by_id.is_(None))).all())
    eligible=[c for c in clients if c.id not in flagged]
    if not eligible:raise HTTPException(status_code=409,detail='No assigned clients without open flags are available for a random control review')
    import secrets
    chosen=secrets.choice(eligible)
    row=PilotSession(organization_id=user.organization_id,advisor_id=user.id,investor_id=chosen.id,sampling_method='RANDOM_UNFLAGGED')
    db.add(row);db.commit()
    return {'id':row.id,'investor_id':chosen.id,'investor_name':chosen.display_name,'sampling_method':row.sampling_method,'note':'Uniform random sample among currently unflagged assigned clients. Human review is needed; this does not establish a population false-negative rate.'}


@router.get('/investors/{iid}/timeline')
def client_timeline(iid:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    scope(db,user,iid);items=[]
    for model,kind,timefield,textfield in [(AdviceRecord,'ADVICE','created_at','recommendation'),(MeetingNote,'MEETING','created_at','approved_summary'),(FollowUpTask,'FOLLOW_UP','created_at','title'),(AttentionCase,'REVIEW','created_at','title')]:
        rows=db.scalars(select(model).where(model.organization_id==user.organization_id,model.investor_id==iid)).all()
        for row in rows:items.append({'id':row.id,'kind':kind,'date':getattr(row,timefield).isoformat(),'text':getattr(row,textfield) or 'Unapproved meeting draft','status':row.status})
    return {'items':sorted(items,key=lambda x:(x['date'],x['id']),reverse=True)[:100]}


@router.post('/reviews/refresh')
def refresh_reviews(request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Advisor refresh required')
    from app.services.monitoring import refresh_clients
    return refresh_clients(db,user)
