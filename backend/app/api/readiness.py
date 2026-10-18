"""Phase 9: scoped, read-only release and demo readiness.

This endpoint never seeds records or starts AI model inference.  A missing item
means it has not been demonstrated in this organization's stored evidence.
"""
from __future__ import annotations
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy import select, func
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import current_user
from app.models import (User, Investor, Holding, ImportBatch, PatternRun,
                        DetectedPattern, PatternMember, AttentionCase,
                        AdviceRecord, FollowUpTask, LocalAIBrief, MeetingNote, AuditEvent)

router = APIRouter(tags=['Demo Readiness'])


def count(db: Session, entity, *predicates) -> int:
    return int(db.scalar(select(func.count()).select_from(entity).where(*predicates)) or 0)


def readiness_snapshot(db: Session, user: User) -> dict:
    org = user.organization_id
    iq = select(Investor.id).where(Investor.organization_id == org)
    if user.role == 'ADVISOR':
        iq = iq.where(Investor.advisor_id == user.id)
    investor_ids = iq.subquery()
    # Every client entity check is scoped to authorized investor IDs as well as organization.
    member_condition = Investor.id.in_(select(investor_ids.c.id))
    investors = count(db, Investor, Investor.organization_id == org, member_condition)
    holdings = count(db, Holding, Holding.organization_id == org, Holding.investor_id.in_(select(investor_ids.c.id)))
    # Import bookkeeping is supervisor-only; advisor responses never disclose org-wide counts.
    committed_imports = (count(db, ImportBatch, ImportBatch.organization_id == org,
                               ImportBatch.status == 'COMMITTED') if user.role == 'SUPERVISOR' else None)
    runs = (count(db, PatternRun, PatternRun.organization_id == org) if user.role == 'SUPERVISOR' else None)
    pattern_ids_q = select(DetectedPattern.id).where(DetectedPattern.organization_id == org)
    if user.role == 'ADVISOR':
        pattern_ids_q = pattern_ids_q.where(DetectedPattern.id.in_(select(PatternMember.pattern_id).where(
            PatternMember.investor_id.in_(select(investor_ids.c.id)))))
    pattern_count = count(db, DetectedPattern, DetectedPattern.id.in_(pattern_ids_q))
    cases = count(db, AttentionCase, AttentionCase.organization_id == org,
                  AttentionCase.investor_id.in_(select(investor_ids.c.id)))
    submitted = count(db, AdviceRecord, AdviceRecord.organization_id == org,
                      AdviceRecord.investor_id.in_(select(investor_ids.c.id)),
                      AdviceRecord.status.in_(['SUBMITTED', 'APPROVED']))
    approved = count(db, AdviceRecord, AdviceRecord.organization_id == org,
                     AdviceRecord.investor_id.in_(select(investor_ids.c.id)), AdviceRecord.status == 'APPROVED')
    tasks = count(db, FollowUpTask, FollowUpTask.organization_id == org,
                  FollowUpTask.investor_id.in_(select(investor_ids.c.id)))
    completed = count(db, FollowUpTask, FollowUpTask.organization_id == org,
                      FollowUpTask.investor_id.in_(select(investor_ids.c.id)), FollowUpTask.status == 'DONE',
                      FollowUpTask.evidence_type.in_(['ADVISOR_ATTESTATION', 'SOURCE_REFERENCE']))
    briefs = count(db, LocalAIBrief, LocalAIBrief.organization_id == org,
                   LocalAIBrief.investor_id.in_(select(investor_ids.c.id)))
    approved_notes = count(db, MeetingNote, MeetingNote.organization_id == org,
                           MeetingNote.investor_id.in_(select(investor_ids.c.id)), MeetingNote.status == 'APPROVED')
    audits = count(db, AuditEvent, AuditEvent.organization_id == org,
                   *( [AuditEvent.actor_id == user.id] if user.role == 'ADVISOR' else [] ))

    def item(key: str, label: str, passed: bool, detail: str, route: str) -> dict:
        return {'key':key, 'label':label, 'ready':passed, 'detail':detail, 'route':route}

    checks = [
        item('access','Authenticated and scoped access',True,'Role-scoped client data is available to this session.','/'),
        item('data','Imported investors and dated holdings',investors > 0 and holdings > 0,
             f'{investors} accessible investors; {holdings} recorded holdings.','/investors'),
        item('patterns','Cross-client pattern detection',pattern_count > 0,
             f'{pattern_count} visible pattern records.' + (f' {runs} organization scan(s).' if runs is not None else ''),'/patterns'),
        item('attention','Evidence-linked review cases',cases > 0,f'{cases} visible cases.','/attention'),
        item('advice','Advisor recommendation submitted',submitted > 0,
             f'{submitted} submitted or approved recommendations.','/advice'),
        item('approval','Finalized recommendation',approved > 0,
             f'{approved} approved recommendation(s).','/advice'),
        item('followup','Verified follow-up evidence',completed > 0,
             f'{completed} completed task(s) with evidence; {tasks} total tasks.','/advice'),
        item('audit','Traceable actions',audits > 0, f'{audits} accessible audit events.','/audit'),
    ]
    required_ready = sum(1 for check in checks if check['ready'])
    return {
        'phase': 9, 'role': user.role, 'generated_at': datetime.now(timezone.utc).isoformat(),
        'overview': {'investor_count':investors, 'holding_count':holdings,
                     'committed_import_count':committed_imports, 'pattern_count':pattern_count,
                     'attention_case_count':cases, 'approved_advice_count':approved,
                     'verified_task_count':completed, 'local_brief_count':briefs,
                     'approved_note_count':approved_notes},
        'checks':checks, 'ready_count': required_ready, 'total_checks':len(checks),
        'workflow_evidence_ready':required_ready == len(checks),
        'optional_ai':{'briefs_created':briefs, 'approved_meeting_notes':approved_notes,
                       'status':'RECORDED_EVIDENCE_ONLY',
                       'note':'Local model installation, live inference and offline availability must be tested separately.'},
        'finance_safeguards':{
            'portfolio_return':'NOT_ASSESSABLE without verified cash flows and approved benchmark',
            'allocation_pattern':'REVIEW SIGNAL, not a suitability verdict',
            'demo_actions':'New advice and meeting notes are illustrative unless verified independently'},
        'note':'Read-only organizational demonstration readiness, NOT production certification. '
               'Past evidence is not the same as a live model or UI integration test.'
    }


@router.get('/demo/readiness')
def readiness(user: User = Depends(current_user), db: Session = Depends(get_db)):
    return readiness_snapshot(db, user)
