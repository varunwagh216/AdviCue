"""Phases 5 and 6: access-controlled attention cases, advice approvals and follow-up tasks.

Financial review signals are not recommendations. Draft advice must be written
by the assigned advisor and submitted for supervisor review before tasks can
be created. Approval is not authorization to trade or proof of performance.
"""
from __future__ import annotations
import json
from datetime import date, datetime, timezone
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import current_user, csrf_protected, require_same_origin
from app.models import (AttentionCase, AdviceRecord, FollowUpTask, AuditEvent,
                        Investor, User, MeetingNote, Organization)

router=APIRouter(tags=['Attention & Advice'])


def _now():return datetime.now(timezone.utc)


def _log(db:Session,user:User,action:str,entity_type:str,entity_id:str,detail:dict|None=None):
    db.add(AuditEvent(organization_id=user.organization_id,actor_id=user.id,
                      action=action,entity_type=entity_type,entity_id=entity_id,
                      detail=json.dumps(detail or {},sort_keys=True)))


def _case(db:Session,user:User,case_id:str)->AttentionCase:
    q=select(AttentionCase).join(Investor,Investor.id==AttentionCase.investor_id).where(
        AttentionCase.id==case_id,
        AttentionCase.organization_id==user.organization_id,
        Investor.organization_id==user.organization_id)
    if user.role=='ADVISOR':q=q.where(Investor.advisor_id==user.id)
    c=db.scalar(q)
    if not c:raise HTTPException(status_code=404,detail='Attention case not found')
    return c


def _advice(db:Session,user:User,record_id:str)->AdviceRecord:
    q=select(AdviceRecord).join(Investor,Investor.id==AdviceRecord.investor_id).where(
        AdviceRecord.id==record_id,AdviceRecord.organization_id==user.organization_id,
        Investor.organization_id==user.organization_id)
    if user.role=='ADVISOR':q=q.where(Investor.advisor_id==user.id)
    row=db.scalar(q)
    if not row:raise HTTPException(status_code=404,detail='Advice not found')
    return row


def _task(db:Session,user:User,task_id:str)->FollowUpTask:
    q=select(FollowUpTask).join(Investor,Investor.id==FollowUpTask.investor_id).where(
        FollowUpTask.id==task_id,FollowUpTask.organization_id==user.organization_id,
        Investor.organization_id==user.organization_id)
    if user.role=='ADVISOR':q=q.where(Investor.advisor_id==user.id,FollowUpTask.owner_id==user.id)
    row=db.scalar(q)
    if not row:raise HTTPException(status_code=404,detail='Follow-up task not found')
    return row


def _public_case(row:AttentionCase)->dict:
    return {'id':row.id,'investor_id':row.investor_id,'advisor_id':row.advisor_id,
            'pattern_id':row.pattern_id,'rule_id':row.rule_id,'rule_version':row.rule_version,
            'source_date':row.source_date.isoformat(),'priority':row.priority,
            'status':row.status,'title':row.title,'reason':row.reason,
            'suggested_action':row.suggested_action,'evidence_source_row_ids':row.evidence_source_row_ids,
            'created_at':row.created_at.isoformat(),'updated_at':row.updated_at.isoformat(),
            'resolved_at':row.resolved_at.isoformat() if row.resolved_at else None,
            'resolution_note':row.resolution_note,
            'superseded_by_id':row.superseded_by_id,
            'data_note':'Historical dated observation; confirm current holdings and mandate. Not a suitability determination.'}


def _public_advice(row:AdviceRecord,db:Session|None=None)->dict:
    return {'id':row.id,'investor_id':row.investor_id,'investor_name':db.get(Investor,row.investor_id).display_name if db else None,'advisor_id':row.advisor_id,
            'alert_id':row.alert_id,'status':row.status,'recommendation':row.recommendation,
            'rationale':row.rationale,'assumptions':row.assumptions,
            'evidence_source_row_ids':row.evidence_source_row_ids,'created_at':row.created_at.isoformat(),
            'submitted_at':row.submitted_at.isoformat() if row.submitted_at else None,
            'decided_at':row.decided_at.isoformat() if row.decided_at else None,
            'decided_by':row.decided_by,'decision_note':row.decision_note,
            'supersedes_id':row.supersedes_id, 'source_meeting_id':row.source_meeting_id,
            'expected_outcome':row.expected_outcome,'review_date':row.review_date.isoformat() if row.review_date else None,
            'review_trigger':row.review_trigger,'outcome_rule':row.outcome_rule}


def _public_task(row:FollowUpTask,db:Session|None=None)->dict:
    overdue=row.status in ('OPEN','IN_PROGRESS') and row.due_date<date.today()
    return {'id':row.id,'investor_id':row.investor_id,'investor_name':db.get(Investor,row.investor_id).display_name if db else None,'advice_id':row.advice_id,'source_meeting_id':row.source_meeting_id,
            'owner_id':row.owner_id,'title':row.title,'due_date':row.due_date.isoformat(),
            'status':row.status,'display_status':'OVERDUE' if overdue else row.status,
            'completion_note':row.completion_note,'evidence_type':row.evidence_type,
            'evidence_reference':row.evidence_reference,
            'created_at':row.created_at.isoformat(), 'updated_at':row.updated_at.isoformat(),
            'completed_at':row.completed_at.isoformat() if row.completed_at else None}


@router.get('/attention')
def list_attention(status:Literal['ALL','OPEN','IN_REVIEW','NEEDS_DATA','RESOLVED']='ALL',
                   include_history:bool=False,
                   user:User=Depends(current_user),db:Session=Depends(get_db)):
    q=select(AttentionCase).join(Investor,Investor.id==AttentionCase.investor_id).where(
        AttentionCase.organization_id==user.organization_id,Investor.organization_id==user.organization_id)
    if user.role=='ADVISOR':q=q.where(Investor.advisor_id==user.id)
    if status!='ALL':q=q.where(AttentionCase.status==status)
    if not include_history:q=q.where(AttentionCase.superseded_by_id.is_(None))
    rows=db.scalars(q.order_by(AttentionCase.priority.asc(),AttentionCase.created_at.desc(),AttentionCase.investor_id).limit(500)).all()
    from app.engines.advanced import reported_comparison, priority_components
    from app.models import PerformanceSnapshot, Holding
    from app.engines.financial import allocation_for_holdings
    today=date.today()
    items=[]
    for row in rows:
        inv=db.get(Investor,row.investor_id)
        snaps=db.scalars(select(PerformanceSnapshot).where(PerformanceSnapshot.organization_id==user.organization_id,PerformanceSnapshot.investor_id==row.investor_id)).all()
        held=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id,Holding.investor_id==row.investor_id)).all()
        value=allocation_for_holdings(held).get('total_value')
        triage=priority_components(reported_comparison(snaps),value,inv.goal_target_date,today)
        obligations=db.scalars(select(FollowUpTask).where(FollowUpTask.organization_id==user.organization_id,FollowUpTask.investor_id==row.investor_id,FollowUpTask.status.in_(['OPEN','IN_PROGRESS']))).all()
        reviews=db.scalars(select(AdviceRecord).where(AdviceRecord.organization_id==user.organization_id,AdviceRecord.investor_id==row.investor_id,AdviceRecord.status=='APPROVED',AdviceRecord.review_date<=today)).all()
        overdue=sum(t.due_date<today for t in obligations)
        due_soon=sum(today<=t.due_date<=today+__import__('datetime').timedelta(days=7) for t in obligations)
        urgency=min(40,overdue*20+due_soon*10+len(reviews)*10)
        score=max(triage['score'],35 if triage['band']=='P2' else 0,65 if row.rule_id.startswith('MON_') and row.priority=='P1' else 35 if row.rule_id.startswith(('MON_','MANUAL_')) and row.priority=='P2' else 0)+urgency
        data=_public_case(row)
        if row.priority!='V_VERIFY':data['priority']='P1' if score>=65 else 'P2' if score>=35 else 'P3'
        age=max(0,(today-row.source_date).days)
        data['ranking']={'score':score,'evaluated_on':today.isoformat(),'source_age_days':age,
            'stale_source':age>45,'overdue_tasks':overdue,'due_soon_tasks':due_soon,'due_advice_reviews':len(reviews),
            'components':triage['components'],'obligation_points':urgency,
            'explanation':'Review order combines reported-data signals and due obligations. Source age is shown separately; this is not a loss estimate.'}
        data['investor_name']=inv.display_name
        items.append(data)
    band={'P1':0,'V_VERIFY':1,'P2':2,'P3':3}
    items.sort(key=lambda x:(x['status']=='RESOLVED',band[x['priority']],-x['ranking']['score'],x['investor_id'],x['id']))
    return {'items':items,
            'counts':{k:sum(row.status==k for row in rows) for k in ('OPEN','IN_REVIEW','NEEDS_DATA','RESOLVED')},
            'total_visible':len(rows),'history_included':include_history,
            'note':'Superseded case records remain auditable but are omitted from the current queue. Priorities reflect documented review needs, not client suitability or trading instructions.'}


@router.get('/attention/{case_id}')
def get_attention(case_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return _public_case(_case(db,user,case_id))


class ManualCaseInput(BaseModel):
    investor_id:str
    title:str=Field(min_length=8,max_length=180)
    reason:str=Field(min_length=12,max_length=2000)


@router.post('/attention',status_code=201)
def create_manual_case(payload:ManualCaseInput,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    from app.api.intelligence import investor_scope
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Assigned advisor required')
    inv=investor_scope(db,user,payload.investor_id)
    from uuid import uuid4
    row=AttentionCase(organization_id=user.organization_id,investor_id=inv.id,advisor_id=user.id,
        rule_id='MANUAL_'+uuid4().hex[:20],rule_version='1.0',source_date=date.today(),priority='P2',status='OPEN',
        title=payload.title.strip(),reason=payload.reason.strip(),suggested_action='Review with the client and document an agreed next step.',evidence_source_row_ids=[])
    if len(row.title)<8 or len(row.reason)<12:raise HTTPException(status_code=422,detail='Provide a descriptive title and reason')
    db.add(row);db.flush();_log(db,user,'ADVISOR_REVIEW_CREATED','AttentionCase',row.id)
    db.commit()
    return _public_case(row)


class CaseAction(BaseModel):
    action:Literal['START_REVIEW','REQUEST_DATA','RESOLVE','REOPEN']
    note:str=Field(default='',max_length=2000)


@router.post('/attention/{case_id}/actions')
def action_on_attention(case_id:str,payload:CaseAction,request:Request,
                        user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    row=_case(db,user,case_id)
    if row.superseded_by_id:
        raise HTTPException(status_code=409,detail='Historical case was superseded; open the current review case instead')
    if user.role!='ADVISOR':
        raise HTTPException(status_code=403,detail='Only assigned advisors can update client review cases')
    valid={
        'OPEN':{'START_REVIEW':'IN_REVIEW','REQUEST_DATA':'NEEDS_DATA','RESOLVE':'RESOLVED'},
        'IN_REVIEW':{'REQUEST_DATA':'NEEDS_DATA','RESOLVE':'RESOLVED'},
        'NEEDS_DATA':{'START_REVIEW':'IN_REVIEW','RESOLVE':'RESOLVED'},
        'RESOLVED':{'REOPEN':'OPEN'},
    }
    next_status=valid[row.status].get(payload.action)
    if not next_status:raise HTTPException(status_code=409,detail='Invalid action for current case status')
    note=payload.note.strip()
    if payload.action in ('REQUEST_DATA','RESOLVE','REOPEN') and len(note)<12:
        raise HTTPException(status_code=422,detail='Explain the action in at least 12 characters')
    old=row.status
    row.status=next_status
    row.updated_at=_now()
    if next_status=='RESOLVED':
        row.resolved_at=row.updated_at;row.resolved_by=user.id;row.resolution_note=note
    elif old=='RESOLVED':
        row.resolved_at=None;row.resolved_by=None;row.resolution_note=None
    _log(db,user,'ATTENTION_'+payload.action,'AttentionCase',row.id,
         {'old_status':old,'new_status':next_status,'note':note})
    db.commit()
    return _public_case(row)


@router.get('/advice')
def list_advice(user:User=Depends(current_user),db:Session=Depends(get_db)):
    q=select(AdviceRecord).join(Investor,Investor.id==AdviceRecord.investor_id).where(
        AdviceRecord.organization_id==user.organization_id,Investor.organization_id==user.organization_id)
    if user.role=='ADVISOR':q=q.where(Investor.advisor_id==user.id)
    rows=db.scalars(q.order_by(AdviceRecord.created_at.desc(),AdviceRecord.id.desc()).limit(500)).all()
    return {'items':[_public_advice(row,db) for row in rows], 'total_visible':len(rows)}


@router.get('/advice/{record_id}')
def get_advice(record_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return _public_advice(_advice(db,user,record_id))


class OutcomeRule(BaseModel):
    metric:Literal['equity_pct','fixed_deposit_pct','portfolio_twr_pct','active_return_pp','benchmark_linked_pct']
    comparator:Literal['>=','<=']
    target_pct:float=Field(ge=-10000,le=10000)
    due_date:date
    window_start:date|None=None
    window_end:date|None=None

    @model_validator(mode='after')
    def valid_window(self):
        from app.engines.advice_evidence import PERFORMANCE_METRICS
        if self.metric in PERFORMANCE_METRICS:
            if not self.window_start or not self.window_end or not self.window_start<self.window_end<=self.due_date:
                raise ValueError('Financial objectives need an increasing measurement window ending on or before the review deadline')
            if self.metric!='active_return_pp' and self.target_pct<-100:raise ValueError('Return threshold cannot be below -100%')
        elif not 0<=self.target_pct<=100:raise ValueError('Allocation threshold must be between 0 and 100%')
        return self


def validate_approval_window(row,approved_at):
    rule=row.outcome_rule
    from app.engines.advice_evidence import PERFORMANCE_METRICS
    from app.core.clock import advisor_day
    if rule and rule['metric'] in PERFORMANCE_METRICS and date.fromisoformat(rule['window_start'])<=advisor_day(approved_at):
        raise HTTPException(status_code=422,detail='Approve financial objectives before the measurement window starts. Daily boundaries must begin after the approval date.')


class DraftAdviceInput(BaseModel):
    alert_id:str
    recommendation:str=Field(min_length=12,max_length=3500)
    rationale:str=Field(min_length=12,max_length=3500)
    assumptions:str|None=Field(default=None,max_length=2000)
    supersedes_id:str|None=None
    source_meeting_id:str|None=None
    outcome_rule:OutcomeRule|None=None
    expected_outcome:str|None=Field(default=None,max_length=1500)
    review_date:date|None=None
    review_trigger:str|None=Field(default=None,max_length=300)


@router.post('/advice',status_code=201)
def create_advice(payload:DraftAdviceInput,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Only an assigned advisor can draft advice')
    case=_case(db,user,payload.alert_id)
    if case.superseded_by_id:
        raise HTTPException(status_code=409,detail='Historical case was superseded; choose the current review case')
    if case.status=='RESOLVED':raise HTTPException(status_code=409,detail='Reopen resolved case before recording new advice')
    if payload.supersedes_id:
        previous=_advice(db,user,payload.supersedes_id)
        if previous.investor_id!=case.investor_id or previous.status not in ('APPROVED','REJECTED'):
            raise HTTPException(status_code=422,detail='Only a decided advice record for this investor may be superseded')
    if payload.source_meeting_id:
        note=db.scalar(select(MeetingNote).where(MeetingNote.id==payload.source_meeting_id,
           MeetingNote.organization_id==user.organization_id,
           MeetingNote.advisor_id==user.id,
           MeetingNote.investor_id==case.investor_id,MeetingNote.status=='APPROVED'))
        if not note: raise HTTPException(status_code=422,detail='Approved note from the same assigned investor is required')
    recommendation=payload.recommendation.strip();rationale=payload.rationale.strip()
    if len(recommendation)<12 or len(rationale)<12:raise HTTPException(status_code=422,detail='Recommendation and rationale cannot be blank')
    row=AdviceRecord(organization_id=user.organization_id,investor_id=case.investor_id,
                     advisor_id=user.id,alert_id=case.id,status='DRAFT',
                     recommendation=recommendation,rationale=rationale,
                     assumptions=payload.assumptions.strip() if payload.assumptions else None,
                     evidence_source_row_ids=list(case.evidence_source_row_ids),
                     supersedes_id=payload.supersedes_id,source_meeting_id=payload.source_meeting_id,
                     expected_outcome=payload.expected_outcome.strip() if payload.expected_outcome else None,
                     review_date=payload.review_date,
                     review_trigger=payload.review_trigger.strip() if payload.review_trigger else None,
                     outcome_rule=payload.outcome_rule.model_dump(mode='json') if payload.outcome_rule else None)
    db.add(row);db.flush()
    _log(db,user,'ADVICE_DRAFT_CREATED','AdviceRecord',row.id,{'alert_id':case.id,'investor_id':case.investor_id})
    db.commit()
    return _public_advice(row,db)


class DraftEditInput(BaseModel):
    recommendation:str=Field(min_length=12,max_length=3500)
    rationale:str=Field(min_length=12,max_length=3500)
    assumptions:str|None=Field(default=None,max_length=2000)


@router.post('/advice/{record_id}/edit')
def edit_advice(record_id:str,payload:DraftEditInput,request:Request,
                user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    row=_advice(db,user,record_id)
    if user.role!='ADVISOR' or row.advisor_id!=user.id:raise HTTPException(status_code=403,detail='Assigned advisor required')
    if row.status!='DRAFT':raise HTTPException(status_code=409,detail='Only drafts can be edited')
    row.recommendation=payload.recommendation.strip();row.rationale=payload.rationale.strip()
    if len(row.recommendation)<12 or len(row.rationale)<12:raise HTTPException(status_code=422,detail='Required fields cannot be blank')
    row.assumptions=payload.assumptions.strip() if payload.assumptions else None
    _log(db,user,'ADVICE_DRAFT_EDITED','AdviceRecord',row.id)
    db.commit()
    return _public_advice(row,db)


@router.post('/advice/{record_id}/submit')
def submit_advice(record_id:str,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    row=_advice(db,user,record_id)
    if user.role!='ADVISOR' or row.advisor_id!=user.id:raise HTTPException(status_code=403,detail='Assigned advisor required')
    if row.status!='DRAFT':raise HTTPException(status_code=409,detail='Only draft advice can be submitted')
    row.status='SUBMITTED';row.submitted_at=_now()
    _log(db,user,'ADVICE_SUBMITTED','AdviceRecord',row.id)
    db.commit()
    return _public_advice(row,db)


class FinalizeInput(BaseModel):
    note: str = Field(min_length=12,max_length=2000)


@router.post('/advice/{record_id}/finalize')
def advisor_finalize(record_id:str,payload:FinalizeInput,request:Request,
                     user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    """Advisor finalization is permitted only when the organization's approval gate is off.

    This is still a human advisor decision, not an LLM or automatic trade action.
    The approved revision remains immutable as with supervisor approval.
    """
    require_same_origin(request)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Assigned advisor required')
    row=_advice(db,user,record_id)
    if row.advisor_id!=user.id:raise HTTPException(status_code=403,detail='Assigned advisor required')
    org=db.get(Organization,user.organization_id)
    if org is None:raise HTTPException(status_code=404,detail='Organization unavailable')
    if org.approval_required:
        raise HTTPException(status_code=403,detail='Admin approval is required by organization policy')
    if row.status not in ('DRAFT','SUBMITTED'):
        raise HTTPException(status_code=409,detail='Only a draft or submitted recommendation can be finalized')
    note=payload.note.strip()
    if len(note)<12:raise HTTPException(status_code=422,detail='Finalization note must contain at least 12 characters')
    approved_at=_now();validate_approval_window(row,approved_at)
    row.status='APPROVED';row.decided_at=approved_at;row.decided_by=user.id;row.decision_note=note
    _log(db,user,'ADVICE_ADVISOR_FINALIZED','AdviceRecord',row.id,{'note':note,'approval_required':False})
    db.commit()
    return _public_advice(row,db)


class DecisionInput(BaseModel):
    note:str=Field(min_length=12,max_length=2000)


@router.post('/advice/{record_id}/approve')
def approve_advice(record_id:str,payload:DecisionInput,request:Request,
                   user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    if user.role!='SUPERVISOR':raise HTTPException(status_code=403,detail='Admin approval required')
    row=_advice(db,user,record_id)
    if row.status!='SUBMITTED':raise HTTPException(status_code=409,detail='Only submitted advice can be approved')
    note=payload.note.strip()
    if len(note)<12:raise HTTPException(status_code=422,detail='Approval note must have at least 12 characters')
    approved_at=_now();validate_approval_window(row,approved_at)
    row.status='APPROVED';row.decided_at=approved_at;row.decided_by=user.id;row.decision_note=note
    _log(db,user,'ADVICE_APPROVED','AdviceRecord',row.id,{'note':note})
    db.commit()
    return _public_advice(row,db)


@router.post('/advice/{record_id}/reject')
def reject_advice(record_id:str,payload:DecisionInput,request:Request,
                  user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    if user.role!='SUPERVISOR':raise HTTPException(status_code=403,detail='Admin approval required')
    row=_advice(db,user,record_id)
    if row.status!='SUBMITTED':raise HTTPException(status_code=409,detail='Only submitted advice can be rejected')
    note=payload.note.strip()
    if len(note)<12:raise HTTPException(status_code=422,detail='Rejection note must have at least 12 characters')
    row.status='REJECTED';row.decided_at=_now();row.decided_by=user.id;row.decision_note=note
    _log(db,user,'ADVICE_REJECTED','AdviceRecord',row.id,{'note':note})
    db.commit()
    return _public_advice(row,db)


@router.get('/tasks')
def list_tasks(user:User=Depends(current_user),db:Session=Depends(get_db)):
    q=select(FollowUpTask).join(Investor,Investor.id==FollowUpTask.investor_id).where(
        FollowUpTask.organization_id==user.organization_id,Investor.organization_id==user.organization_id)
    if user.role=='ADVISOR':q=q.where(Investor.advisor_id==user.id,FollowUpTask.owner_id==user.id)
    rows=db.scalars(q.order_by(FollowUpTask.due_date,FollowUpTask.id).limit(500)).all()
    return {'items':[_public_task(row,db) for row in rows],'total_visible':len(rows)}


class TaskInput(BaseModel):
    advice_id:str|None=None
    source_meeting_id:str|None=None
    commitment_index:int|None=Field(default=None,ge=0)
    title:str=Field(min_length=8,max_length=200)
    due_date:date


@router.post('/tasks',status_code=201)
def create_task(payload:TaskInput,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Only assigned advisors can create client tasks')
    if bool(payload.advice_id)==bool(payload.source_meeting_id):
        raise HTTPException(status_code=422,detail='Choose either approved advice or an approved meeting commitment')
    advice=None
    if payload.advice_id:
        advice=_advice(db,user,payload.advice_id)
        if advice.advisor_id!=user.id or advice.status!='APPROVED':
            raise HTTPException(status_code=409,detail='An approved recommendation is required before creating tasks')
        investor_id=advice.investor_id
    else:
        from app.api.local_ai import _meeting
        note=_meeting(db,user,payload.source_meeting_id)
        if note.status!='APPROVED' or payload.commitment_index is None or payload.commitment_index>=len(note.approved_commitments or []):
            raise HTTPException(status_code=422,detail='Choose a commitment from an approved meeting')
        investor_id=note.investor_id
        if payload.title.strip()!=note.approved_commitments[payload.commitment_index].strip():
            raise HTTPException(status_code=422,detail='Meeting task must preserve the approved commitment text')
    if payload.due_date<date.today():raise HTTPException(status_code=422,detail='Select today or a future due date')
    title=payload.title.strip()
    if len(title)<8:raise HTTPException(status_code=422,detail='Task title must contain at least 8 characters')
    task=FollowUpTask(organization_id=user.organization_id,investor_id=investor_id,
                      advice_id=advice.id if advice else None,source_meeting_id=payload.source_meeting_id,owner_id=user.id,title=title,due_date=payload.due_date,status='OPEN')
    db.add(task);db.flush()
    _log(db,user,'FOLLOW_UP_CREATED','FollowUpTask',task.id,{'advice_id':advice.id if advice else None,'meeting_id':payload.source_meeting_id,'commitment_index':payload.commitment_index,'due_date':payload.due_date.isoformat()})
    db.commit()
    return _public_task(task,db)


class TaskUpdate(BaseModel):
    status:Literal['IN_PROGRESS','DONE','CANNOT_VERIFY']
    note:str=Field(default='',max_length=3000)
    evidence_type:Literal['ADVISOR_ATTESTATION','SOURCE_REFERENCE']|None=None
    evidence_reference:str|None=Field(default=None,max_length=500)


@router.post('/tasks/{task_id}/status')
def update_task(task_id:str,payload:TaskUpdate,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    row=_task(db,user,task_id)
    if user.role!='ADVISOR' or row.owner_id!=user.id:raise HTTPException(status_code=403,detail='Assigned task owner required')
    if row.status in ('DONE','CANNOT_VERIFY'):
        raise HTTPException(status_code=409,detail='Completed task cannot be altered; create a new follow-up')
    if row.status=='IN_PROGRESS' and payload.status=='IN_PROGRESS':
        raise HTTPException(status_code=409,detail='Task is already in progress')
    note=payload.note.strip()
    if payload.status in ('DONE','CANNOT_VERIFY') and len(note)<12:
        raise HTTPException(status_code=422,detail='Completion/verification note must be at least 12 characters')
    if payload.status=='DONE':
        if payload.evidence_type not in ('ADVISOR_ATTESTATION','SOURCE_REFERENCE'):
            raise HTTPException(status_code=422,detail='Completion requires an evidence type')
        if payload.evidence_type=='SOURCE_REFERENCE' and not (payload.evidence_reference or '').strip():
            raise HTTPException(status_code=422,detail='A source reference is required for this evidence type')
    row.status=payload.status;row.updated_at=_now()
    if row.status in ('DONE','CANNOT_VERIFY'):
        row.completed_at=row.updated_at
        row.completion_note=note
        row.evidence_type=payload.evidence_type if row.status=='DONE' else None
        row.evidence_reference=payload.evidence_reference.strip() if payload.evidence_reference else None
    _log(db,user,'FOLLOW_UP_'+row.status,'FollowUpTask',row.id,
         {'note':note,'evidence_type':row.evidence_type,'evidence_reference':row.evidence_reference})
    db.commit()
    return _public_task(row,db)


@router.get('/tasks/{task_id}')
def task_detail(task_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    return _public_task(_task(db,user,task_id),db)


@router.get('/audit-events')
def list_audit_events(user:User=Depends(current_user),db:Session=Depends(get_db)):
    q=select(AuditEvent).where(AuditEvent.organization_id==user.organization_id)
    # Advisor can only view actions they took themselves; supervisor can audit org-wide.
    if user.role=='ADVISOR':q=q.where(AuditEvent.actor_id==user.id)
    rows=db.scalars(q.order_by(AuditEvent.created_at.desc()).limit(100)).all()
    return {'items':[{'action':x.action,'entity_type':x.entity_type,'entity_id':x.entity_id,
                      'created_at':x.created_at.isoformat()} for x in rows],
            'scope':'ORGANIZATION' if user.role=='SUPERVISOR' else 'OWN_ACTIONS'}


@router.get('/advice/{record_id}/outcome')
def advice_outcome_review(record_id:str,user:User=Depends(current_user),db:Session=Depends(get_db),evidence_id:str|None=None):
    from app.models import PerformanceSnapshot
    from app.engines.advanced import advice_outcome, reported_peer_comparison
    advice=_advice(db,user,record_id)
    snapshots=db.scalars(select(PerformanceSnapshot).where(PerformanceSnapshot.organization_id==user.organization_id,
        PerformanceSnapshot.investor_id==advice.investor_id)).all()
    peer_result=None
    if advice.status=='APPROVED':
        original=db.get(Investor,advice.investor_id)
        peers=db.scalars(select(Investor).where(Investor.organization_id==user.organization_id,
                     Investor.id!=advice.investor_id,Investor.risk_profile==original.risk_profile)).all()
        if peers:
            from app.models import PerformanceSnapshot
            since=(advice.decided_at or advice.submitted_at).date()
            snap_peers=db.scalars(select(PerformanceSnapshot).where(PerformanceSnapshot.organization_id==user.organization_id,
                     PerformanceSnapshot.investor_id.in_([i.id for i in peers]),PerformanceSnapshot.snapshot_date>since)).all()
            peer_result=reported_peer_comparison(snapshots,snap_peers)
    from app.models import Holding
    from app.engines.advanced import evaluate_advice_rule
    held=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id,Holding.investor_id==advice.investor_id)).all()
    tasks=db.scalars(select(FollowUpTask).where(FollowUpTask.advice_id==advice.id,FollowUpTask.organization_id==user.organization_id)).all()
    execution=evaluate_advice_rule(advice,held)
    from app.models import ReviewEvidence,AdviceOutcomeReview
    from app.engines.advice_evidence import objective_review
    evidence=db.scalars(select(ReviewEvidence).where(ReviewEvidence.organization_id==user.organization_id,ReviewEvidence.investor_id==advice.investor_id,ReviewEvidence.status=='APPROVED')).all()
    reviews=db.scalars(select(AdviceOutcomeReview).where(AdviceOutcomeReview.organization_id==user.organization_id,AdviceOutcomeReview.advice_id==advice.id).order_by(AdviceOutcomeReview.created_at.desc())).all()
    if evidence_id and evidence_id not in {e.id for e in evidence}:raise HTTPException(status_code=404,detail='Approved evidence not found for this client')
    return {'agreed_objective':objective_review(advice,held,evidence,evidence_id=evidence_id),'saved_reviews':[{'id':r.id,'created_at':r.created_at.isoformat(),'result':r.result,'note':r.note} for r in reviews],
            'condition_check':execution,'task_completion':{'total':len(tasks),'done':sum(t.status=='DONE' for t in tasks),
            'note':'Task completion alone does not verify a portfolio change.'},
            'peer_comparison':peer_result,'advice_id':advice.id,'investor_id':advice.investor_id,
            'expected_outcome':advice.expected_outcome,
            'review_date':advice.review_date.isoformat() if advice.review_date else None,
            'review_trigger':advice.review_trigger,
            'review_due':bool(advice.review_date and advice.review_date<=date.today()),
            'follow_up_required':bool(advice.review_date and advice.review_date<=date.today()),
            **advice_outcome(advice,snapshots)}


class OutcomeReviewInput(BaseModel):
    evidence_id:str|None=None
    note:str=Field(min_length=20,max_length=2000)


@router.post('/advice/{record_id}/outcome-reviews',status_code=201)
def save_outcome_review(record_id:str,payload:OutcomeReviewInput,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request);advice=_advice(db,user,record_id)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Assigned advisor required')
    if advice.status!='APPROVED':raise HTTPException(status_code=409,detail='Approved advice required')
    if len(payload.note.strip())<20:raise HTTPException(status_code=422,detail='Explain the review in at least 20 characters')
    from app.models import ReviewEvidence,AdviceOutcomeReview,Holding
    from app.engines.advice_evidence import objective_review
    evidence=db.scalars(select(ReviewEvidence).where(ReviewEvidence.organization_id==user.organization_id,ReviewEvidence.investor_id==advice.investor_id,ReviewEvidence.status=='APPROVED')).all()
    if payload.evidence_id and payload.evidence_id not in {e.id for e in evidence}:raise HTTPException(status_code=404,detail='Approved evidence not found for this client')
    held=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id,Holding.investor_id==advice.investor_id)).all()
    result=objective_review(advice,held,evidence,evidence_id=payload.evidence_id)
    row=AdviceOutcomeReview(organization_id=user.organization_id,investor_id=advice.investor_id,advisor_id=user.id,advice_id=advice.id,evidence_id=result['evidence_id'],result=result,note=payload.note.strip())
    db.add(row);db.flush();_log(db,user,'ADVICE_OUTCOME_REVIEWED','AdviceOutcomeReview',row.id,{'advice_id':advice.id,'status':result['status'],'evidence_id':row.evidence_id})
    db.commit();return {'id':row.id,'result':result,'note':row.note,'created_at':row.created_at.isoformat()}
