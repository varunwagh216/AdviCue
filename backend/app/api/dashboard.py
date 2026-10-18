from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import current_user
from app.core.access import may_import, may_run_org_scan
from app.models import Holding, ImportBatch, InvestmentTransaction, Investor, PerformanceSnapshot, User, PatternRun, PatternMember, AttentionCase, AdviceRecord, FollowUpTask

router = APIRouter(tags=['Investor records and dashboard'])


def scoped_investors(db:Session,user:User):
    query=select(Investor).where(Investor.organization_id==user.organization_id)
    if user.role=='ADVISOR':
        query=query.where(Investor.advisor_id==user.id)
    return query


@router.get('/dashboard')
def dashboard(user:User=Depends(current_user),db:Session=Depends(get_db)):
    invest_query=select(func.count()).select_from(Investor).where(Investor.organization_id==user.organization_id)
    if user.role=='ADVISOR':
        invest_query=invest_query.where(Investor.advisor_id==user.id)
    count=db.scalar(invest_query) or 0
    latest_import=None
    if user.role=='SUPERVISOR':
        latest=db.scalar(select(ImportBatch).where(ImportBatch.organization_id==user.organization_id)
                         .order_by(ImportBatch.created_at.desc()).limit(1))
        if latest:
            latest_import={'id':latest.id,'status':latest.status,'filename':latest.filename,
                           'warnings':latest.warning_count,'errors':latest.error_count}
    latest_pattern_run=db.scalar(select(PatternRun).where(PatternRun.organization_id==user.organization_id)
                  .order_by(PatternRun.created_at.desc(),PatternRun.id.desc()).limit(1))
    pattern_count=0
    if latest_pattern_run:
        from app.models import DetectedPattern
        pq=select(func.count()).select_from(DetectedPattern).where(DetectedPattern.run_id==latest_pattern_run.id)
        if user.role=='ADVISOR':
            pq=pq.join(PatternMember,PatternMember.pattern_id==DetectedPattern.id).join(Investor,Investor.id==PatternMember.investor_id).where(Investor.organization_id==user.organization_id,Investor.advisor_id==user.id)
        pattern_count=db.scalar(pq) or 0
    caseq=select(func.count()).select_from(AttentionCase).join(Investor, Investor.id==AttentionCase.investor_id).where(
        AttentionCase.organization_id==user.organization_id,Investor.organization_id==user.organization_id,
        AttentionCase.status!='RESOLVED',AttentionCase.superseded_by_id.is_(None))
    adviceq=select(func.count()).select_from(AdviceRecord).join(Investor, Investor.id==AdviceRecord.investor_id).where(
        AdviceRecord.organization_id==user.organization_id,Investor.organization_id==user.organization_id)
    taskq=select(func.count()).select_from(FollowUpTask).join(Investor, Investor.id==FollowUpTask.investor_id).where(
        FollowUpTask.organization_id==user.organization_id,Investor.organization_id==user.organization_id,
        FollowUpTask.status.in_(['OPEN','IN_PROGRESS']))
    if user.role=='ADVISOR':
        caseq=caseq.where(Investor.advisor_id==user.id)
        adviceq=adviceq.where(Investor.advisor_id==user.id)
        taskq=taskq.where(Investor.advisor_id==user.id,FollowUpTask.owner_id==user.id)
    return {
        'investor_count':count,'attention_count':db.scalar(caseq) or 0,'pattern_count':pattern_count,
        'advice_count':db.scalar(adviceq) or 0,'open_tasks_count':db.scalar(taskq) or 0,
        'latest_import':latest_import,
        'modules':[
            {'name':'Data Trust','status':'READY'},
            {'name':'Financial Intelligence','status':'READY'},
            {'name':'Pattern Detection','status':'READY'},
            {'name':'Attention Radar','status':'READY'},
            {'name':'Advice Ledger','status':'READY'},
            {'name':'Local AI','status':'READY'},
            {'name':'Security and Audit','status':'READY'},
        ],
        'as_of':datetime.now(timezone.utc).isoformat(),
    }


@router.get('/investors')
def list_investors(user:User=Depends(current_user),db:Session=Depends(get_db)):
    rows=db.scalars(scoped_investors(db,user).order_by(Investor.id).limit(500)).all()
    return {'items':[{'id':i.id,'display_name':i.display_name,'risk_profile':i.risk_profile,
                       'advisor_id':i.advisor_id,'source_advisor_code':i.source_advisor_code,
                       'city':i.city,'primary_goal':i.primary_goal} for i in rows],
            'count':len(rows)}


@router.get('/investors/{investor_id}')
def investor_records(investor_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    inv=db.scalar(scoped_investors(db,user).where(Investor.id==investor_id))
    if not inv:
        raise HTTPException(status_code=404,detail='Investor not found')
    holdings=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id,Holding.investor_id==inv.id)
                       .order_by(Holding.as_of_date.desc(),Holding.external_holding_id)).all()
    tx_count=db.scalar(select(func.count()).select_from(InvestmentTransaction).where(
        InvestmentTransaction.organization_id==user.organization_id,
        InvestmentTransaction.investor_id==inv.id)) or 0
    snap_count=db.scalar(select(func.count()).select_from(PerformanceSnapshot).where(
        PerformanceSnapshot.organization_id==user.organization_id,
        PerformanceSnapshot.investor_id==inv.id)) or 0
    return {
        'investor':{'id':inv.id,'display_name':inv.display_name,'risk_profile':inv.risk_profile,
                    'age':inv.age,'source_advisor_code':inv.source_advisor_code,'city':inv.city,
                    'primary_goal':inv.primary_goal,'goal_target_amount':str(inv.goal_target_amount) if inv.goal_target_amount is not None else None,
                    'goal_target_date':inv.goal_target_date.isoformat() if inv.goal_target_date else None},
        'holdings':[{'holding_id':h.external_holding_id,'asset_class':h.asset_class,
                     'instrument_name':h.instrument_name,'current_value':str(h.current_value),
                     'as_of_date':h.as_of_date.isoformat(),'source_row_id':h.source_row_id} for h in holdings],
        'transaction_count':tx_count,'snapshot_count':snap_count,
        'performance_status':'NOT_ASSESSABLE',
        'reported_performance_status':'SOURCE_REPORTED_UNVERIFIED' if snap_count else 'NO_SNAPSHOTS',
        'note':'Verified TWR/XIRR remain not assessable from incomplete cash-flow evidence. Dated source-reported benchmark comparison is separately available in investor analysis.',
    }


@router.get('/advisor-capabilities')
def advisor_capabilities(user:User=Depends(current_user),db:Session=Depends(get_db)):
    """Frontend capability flags; each write API independently enforces its guard."""
    from app.models import Organization
    org=db.get(Organization,user.organization_id)
    return {
        'can_manage_workbooks':may_import(user),
        'can_run_group_scan':may_run_org_scan(user),
        'can_finalize_advice':user.role=='ADVISOR' and bool(org) and not org.approval_required,
        'scope':'WORKSPACE_OPERATOR' if may_import(user) and user.role=='ADVISOR' else 'ASSIGNED_CLIENTS',
    }


@router.get('/workspace-summary')
def workspace_summary(user:User=Depends(current_user),db:Session=Depends(get_db)):
    """Dated, advisor-scoped chart facts. No invented portfolio health or returns."""
    from collections import defaultdict
    from decimal import Decimal
    from app.engines.financial import allocation_for_holdings
    clients=db.scalars(scoped_investors(db,user)).all()
    ids=[i.id for i in clients]
    held=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id,Holding.investor_id.in_(ids))).all() if ids else []
    by_client=defaultdict(list)
    for h in held:by_client[h.investor_id].append(h)
    rows=[];risk=defaultdict(int);goals=defaultdict(Decimal);total=Decimal(0)
    for inv in clients:
        a=allocation_for_holdings(by_client[inv.id]);value=Decimal(a['total_value'] or '0')
        total+=value;risk[inv.risk_profile or 'Unspecified']+=1;goals[inv.primary_goal or 'Unspecified']+=value
        rows.append({'id':inv.id,'name':inv.display_name,'value':str(value),'risk_profile':inv.risk_profile,
            'goal':inv.primary_goal,'as_of_date':a['as_of_date'],'equity_pct':a['equity_pct'],'fixed_deposit_pct':a['fixed_deposit_pct']})
    snapshots=db.scalars(select(PerformanceSnapshot).where(PerformanceSnapshot.organization_id==user.organization_id,PerformanceSnapshot.investor_id.in_(ids))).all() if ids else []
    dates=defaultdict(dict)
    for s in snapshots:dates[s.snapshot_date][s.investor_id]=s.portfolio_value
    return {'clients':rows,'recorded_holdings_total':str(total),'risk_counts':dict(risk),
        'goal_values':[{'name':k,'value':str(v)} for k,v in goals.items()],
        'balance_history':[{'date':d.isoformat(),'value':str(sum(v.values(),Decimal(0))),'client_count':len(v)} for d,v in sorted(dates.items())],
        'note':'Latest dated holdings per assigned client. Balances are source-reported, not investment returns. Goal grouping does not imply assets are assigned to goal funding.'}
