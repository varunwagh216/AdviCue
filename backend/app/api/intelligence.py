"""Phase 3 investor intelligence and Phase 4 explainable cross-client patterns.

All investor access goes through the organization/advisor scoping function.
"""
from __future__ import annotations
import json
from datetime import date
from decimal import Decimal
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.dashboard import scoped_investors
from app.core.database import get_db
from app.core.access import may_run_org_scan
from app.core.security import csrf_protected, current_user, require_same_origin
from app.engines.financial import allocation_for_holdings, recorded_value_change, months_remaining, goal_scenarios, money
from app.engines.patterns import detect_low_equity_fd, detect_general_peer_clusters, RULE_VERSION, PATTERN_RULE
from app.engines.advanced import reported_comparison, allocation_peer_explanation, priority_components, behaviour_signals, attributable_gap, advisor_review_agenda, reported_peer_comparison
from app.services.attention import create_or_update_pattern_cases
from app.models import (AuditEvent, DataQualityIssue, DetectedPattern, Holding, Investor,
                        PatternMember, PatternRun, PerformanceSnapshot, User, InvestmentTransaction, AdviceRecord, AttentionCase, AssetClassReturnObservation)

router = APIRouter(tags=['Financial Intelligence & Patterns'])


def investor_scope(db:Session,user:User,investor_id:str) -> Investor:
    inv=db.scalar(scoped_investors(db,user).where(Investor.id==investor_id))
    if not inv: raise HTTPException(status_code=404,detail='Investor not found')
    return inv


def quality_for_holdings(db:Session,rows:list[Holding]) -> list[dict]:
    ids=[h.source_row_id for h in rows]
    if not ids:return []
    issues=db.scalars(select(DataQualityIssue).where(DataQualityIssue.source_row_id.in_(ids)).order_by(DataQualityIssue.code)).all()
    return [{'source_row_id':x.source_row_id,'severity':x.severity,'code':x.code,'message':x.message} for x in issues]


@router.get('/investors/{investor_id}/analysis')
def analysis(investor_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    inv=investor_scope(db,user,investor_id)
    holdings=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id,
                    Holding.investor_id==inv.id)).all()
    allocation=allocation_for_holdings(holdings)
    snap=db.scalars(select(PerformanceSnapshot).where(PerformanceSnapshot.organization_id==user.organization_id,
                    PerformanceSnapshot.investor_id==inv.id).order_by(PerformanceSnapshot.snapshot_date)).all()
    changes=None
    if len(snap)>=2:
        first,last=snap[0],snap[-1]
        changes={'start_date':first.snapshot_date.isoformat(),'end_date':last.snapshot_date.isoformat(),
                 'start_value':money(first.portfolio_value),'end_value':money(last.portfolio_value),
                 'recorded_value_change_pct':recorded_value_change(first.portfolio_value,last.portfolio_value),
                 'warning':'Change in recorded balances is NOT a portfolio investment return; external flows remain unverified.'}
    warnings=quality_for_holdings(db,[h for h in holdings if allocation['as_of_date'] and h.as_of_date.isoformat()==allocation['as_of_date']])
    reported=reported_comparison(snap)
    # Only aggregate comparison with similar-risk peers. Their identities do not leave this route.
    peers=db.scalars(select(Investor).where(Investor.organization_id==user.organization_id,
        Investor.risk_profile==inv.risk_profile,Investor.id!=inv.id)).all()
    peer_ids=[p.id for p in peers]
    peer_holdings=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id,
                            Holding.investor_id.in_(peer_ids))).all() if peer_ids else []
    grouped={pid:[] for pid in peer_ids}
    for holding in peer_holdings:
        if holding.as_of_date.isoformat()==allocation.get('as_of_date'):grouped[holding.investor_id].append(holding)
    peers_allocation=[allocation_for_holdings(grouped[p.id]) for p in peers]
    exposure=allocation_peer_explanation(allocation,peers_allocation)
    triage=priority_components(reported,allocation['total_value'],inv.goal_target_date,
                     date.today())
    transactions=db.scalars(select(InvestmentTransaction).where(InvestmentTransaction.organization_id==user.organization_id,
                                     InvestmentTransaction.investor_id==inv.id)).all()
    signals=behaviour_signals(transactions)
    # Suggest goal assumptions, never quietly equate total portfolio holdings with goal principal.
    sip=[t for t in transactions if t.type.strip().lower()=='sip' and not t.possible_duplicate and t.date_confidence!='QUARANTINED_AMBIGUOUS']
    sip_by_month={}
    for t in sip:sip_by_month.setdefault(t.date.strftime('%Y-%m'),Decimal('0'));sip_by_month[t.date.strftime('%Y-%m')]+=t.amount
    estimated_sip=money(sum(sip_by_month.values(),Decimal('0'))/len(sip_by_month)) if sip_by_month else None
    org_holdings=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id)).all()
    totals={}
    for h in org_holdings:totals.setdefault(h.investor_id,[]).append(h)
    ranked=sorted((Decimal(allocation_for_holdings(h)['total_value'] or '0'),iid) for iid,h in totals.items())
    ranked.reverse()
    position=next((idx for idx,(_,iid) in enumerate(ranked,1) if iid==inv.id),None)
    latest_advice=db.scalars(select(AdviceRecord).where(AdviceRecord.organization_id==user.organization_id,
                          AdviceRecord.investor_id==inv.id,AdviceRecord.status=='APPROVED')).all()
    from app.engines.advanced import advice_outcome
    peer_reported_snap=db.scalars(select(PerformanceSnapshot).where(PerformanceSnapshot.organization_id==user.organization_id,
                                    PerformanceSnapshot.investor_id.in_(peer_ids))).all() if peer_ids else []
    outcomes=[]
    for a in latest_advice:
        outcome=advice_outcome(a,snap)
        if outcome['status']=='OBSERVATIONAL_ONLY':
            start=(a.decided_at or a.submitted_at).date()
            outcome['peer_comparison']=reported_peer_comparison(
                 [r for r in snap if r.snapshot_date>start],
                 [r for r in peer_reported_snap if r.snapshot_date>start])
        outcomes.append({'advice_id':a.id,**outcome})
    # Only when the operator supplied complete sourced return observations do
    # we provide an allocation/return *proxy*. Never pretend it is attribution.
    from app.engines.advanced import sourced_class_return_proxy
    class_returns=db.scalars(select(AssetClassReturnObservation).where(
         AssetClassReturnObservation.organization_id==user.organization_id)).all()
    source_proxy=sourced_class_return_proxy(reported,exposure,class_returns)
    source_health={'ambiguous_date_rows':db.scalar(select(func.count()).select_from(DataQualityIssue).join(
         Holding,Holding.source_row_id==DataQualityIssue.source_row_id).where(Holding.investor_id==inv.id,
            DataQualityIssue.code=='AMBIGUOUS_SOURCE_DATE')) or 0}
    if inv.goal_target_date and inv.goal_target_amount and allocation.get('total_value'):
        future=(inv.goal_target_date-date.today()).days
        source_health['goal_funding_verification_needed']=(0<future<550 and
                Decimal(inv.goal_target_amount)>Decimal(allocation['total_value'])*8)
    else:source_health['goal_funding_verification_needed']=False
    latest_snap=max(snap,key=lambda s:s.snapshot_date) if snap else None
    source_health['different_date_identical_balance']=(bool(latest_snap and allocation.get('as_of_date')) and
        latest_snap.snapshot_date.isoformat()!=allocation['as_of_date'] and
        Decimal(latest_snap.portfolio_value)==Decimal(allocation['total_value']))
    from app.api.evidence import verified_analysis
    reviewed=verified_analysis(inv.id,user,db)
    return {'reviewed_performance':reviewed,'investor_id':inv.id,'risk_profile':inv.risk_profile,'currency':'INR',
            'allocation':allocation,'source_quality_issues':warnings,'reported_comparison':reported,
            'peer_exposure':exposure,'review_agenda':advisor_review_agenda(inv,allocation,reported,signals),'gap_attribution':attributable_gap(allocation,exposure,reported),'source_class_return_proxy':source_proxy,
            'attention_score':triage,'behaviour_signals':signals,
            'long_tail':{'rank_by_recorded_holdings':position,'organization_investors':len(ranked),
                         'method':'Rank by current recorded holdings; does not imply lost returns.'},
            'advice_outcomes':outcomes,'data_trust_summary':source_health,
            'performance':{'status':reviewed['status'] if reviewed.get('portfolio_twr_pct') is not None else 'NOT_ASSESSABLE','reason':reviewed.get('limitations') if reviewed.get('portfolio_twr_pct') is not None else 'External cash-flow classification, complete flow timing and suitable benchmark policy are not verified.',
                           'source_snapshot_count':len(snap),'recorded_balance_change':changes,
                           'benchmark_status':'ADVISOR_REVIEWED_POLICY' if reviewed.get('portfolio_twr_pct') is not None else 'NO_APPROVED_BENCHMARK'},
            'goal':{'target_amount':money(inv.goal_target_amount) if inv.goal_target_amount else None,
                    'target_date':inv.goal_target_date.isoformat() if inv.goal_target_date else None,
                    'status':'INPUTS_REQUIRED' if inv.goal_target_amount and inv.goal_target_date else 'NO_VERIFIED_GOAL',
                    'reason':'Provide goal-assigned opening principal and contributions; total holdings are not automatically goal funds.',
                    'observed_average_monthly_sip':estimated_sip,'monthly_sip_note':'Recorded SIP average across observed contributing months; not a confirmed future goal contribution.'},
            'assessment':'Allocation is descriptive; not proof of risk-policy breach or unsuitable investment advice.'}


class ScenarioInput(BaseModel):
    principal:Decimal=Field(ge=0,le=10**15,decimal_places=2)
    monthly_contribution:Decimal=Field(ge=0,le=10**12,decimal_places=2)
    as_of_date:date
    annual_return_assumptions_pct:list[Decimal]=Field(default_factory=lambda:[Decimal('4'),Decimal('8'),Decimal('12')],min_length=1,max_length=5)


@router.post('/investors/{investor_id}/goal-scenarios')
def project_goal(investor_id:str,payload:ScenarioInput,request:Request,
                 user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    inv=investor_scope(db,user,investor_id)
    if not inv.goal_target_date or not inv.goal_target_amount or inv.goal_target_amount <= 0:
        raise HTTPException(status_code=422,detail='Verified goal target and date are not available for this investor')
    n=months_remaining(payload.as_of_date,inv.goal_target_date)
    if n<=0:raise HTTPException(status_code=422,detail='Goal target date must be after the scenario as-of date')
    if n>1200:raise HTTPException(status_code=422,detail='Goal horizon exceeds 100 years')
    if any(not rate.is_finite() or rate<=-100 or rate>100 for rate in payload.annual_return_assumptions_pct):
        raise HTTPException(status_code=422,detail='Return assumptions must be finite percentages above -100 and at most 100')
    rates=[rate/Decimal('100') for rate in payload.annual_return_assumptions_pct]
    try:
        calculated=goal_scenarios(principal=payload.principal,monthly_contribution=payload.monthly_contribution,
                                  target_amount=inv.goal_target_amount,months=n,annual_rates=rates)
    except (ValueError,ArithmeticError,OverflowError) as exc:
        raise HTTPException(status_code=422,detail=str(exc)) from exc
    return {'investor_id':inv.id,'currency':'INR','as_of_date':payload.as_of_date.isoformat(),
            'target_date':inv.goal_target_date.isoformat(),'target_amount':money(inv.goal_target_amount),
            'goal_assigned_principal':money(payload.principal),
            'monthly_contribution':money(payload.monthly_contribution),
            'months':n,'contribution_timing':'END_OF_MONTH','scenarios':calculated,
            'disclaimer':'Illustrative deterministic scenarios only. Inputs are advisor-supplied and not confirmed source facts. Not statistical probabilities or guaranteed returns.'}


def allowed_pattern(db:Session,user:User,pattern_id:str)->tuple[DetectedPattern,list[PatternMember]]:
    pattern=db.scalar(select(DetectedPattern).where(DetectedPattern.id==pattern_id,
                                                DetectedPattern.organization_id==user.organization_id))
    if not pattern:raise HTTPException(status_code=404,detail='Pattern not found')
    q=select(PatternMember).join(Investor,Investor.id==PatternMember.investor_id).where(
        PatternMember.pattern_id==pattern.id, Investor.organization_id==user.organization_id)
    if user.role=='ADVISOR':q=q.where(Investor.advisor_id==user.id)
    members=db.scalars(q.order_by(PatternMember.investor_id)).all()
    if not members:raise HTTPException(status_code=404,detail='Pattern not found')
    return pattern,members


def pattern_public(pattern:DetectedPattern,members:list[PatternMember],user:User)->dict:
    supervisor=user.role=='SUPERVISOR'
    return {'id':pattern.id,'rule_id':pattern.rule_id,'rule_version':pattern.rule_version,
            'as_of_date':pattern.snapshot_date.isoformat(),# The full-cohort figures are non-identifying aggregates. Names and holding evidence
            # for another advisor's clients NEVER enter the member list.
            'scope':'ORGANIZATION' if supervisor else 'AGGREGATED_WITH_ASSIGNED_DETAILS',
            'member_count':pattern.member_count,
            'advisor_count':pattern.advisor_count,
            'recorded_value_total':money(pattern.recorded_value_total),
            'assigned_member_count':len(members),
            'evidence_summary':pattern.evidence_summary,
            'interpretation':'Review signal only; no automatic suitability or underperformance conclusion.',
            'members':[{'investor_id':m.investor_id,'equity_pct':str(m.equity_pct),
                        'fixed_deposit_pct':str(m.fixed_deposit_pct),'recorded_value':money(m.recorded_value),
                        'source_row_ids':m.evidence_source_row_ids} for m in members]}


@router.post('/patterns/run')
def run_patterns(request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    if not may_run_org_scan(user):raise HTTPException(status_code=403,detail='Cross-advisor scan requires authorized workspace operator')
    investors=db.scalars(select(Investor).where(Investor.organization_id==user.organization_id)).all()
    holdings=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id)).all()
    # Accepted import rows are required. Keep valuation mismatch warnings visible in client analysis.
    snapshots=db.scalars(select(PerformanceSnapshot).where(PerformanceSnapshot.organization_id==user.organization_id)).all()
    grouped_snap={i.id:[] for i in investors}
    for snap in snapshots:grouped_snap[snap.investor_id].append(snap)
    comparisons={iid:reported_comparison(rows) for iid,rows in grouped_snap.items()}
    finding=detect_low_equity_fd(investors,holdings,comparisons=comparisons)
    run=PatternRun(organization_id=user.organization_id,actor_id=user.id,rule_version=RULE_VERSION,
                   as_of_date=date.fromisoformat(finding['as_of_date']) if finding['as_of_date'] else None,
                   matched_count=finding['member_count'] if finding['matched'] else 0)
    db.add(run);db.flush()
    pattern=None
    if finding['matched']:
        pattern=DetectedPattern(run_id=run.id,organization_id=user.organization_id,rule_id=PATTERN_RULE,
              rule_version=RULE_VERSION,snapshot_date=date.fromisoformat(finding['as_of_date']),
              member_count=finding['member_count'],advisor_count=finding['advisor_count'],
              recorded_value_total=Decimal(finding['recorded_value_total']),evidence_summary=finding['reason'])
        db.add(pattern);db.flush()
        for member in finding['members']:
            db.add(PatternMember(pattern_id=pattern.id,investor_id=member['investor_id'],
                 advisor_id=member['advisor_id'],equity_pct=Decimal(member['equity_pct']),
                 fixed_deposit_pct=Decimal(member['fixed_deposit_pct']),
                 recorded_value=Decimal(member['recorded_value']),evidence_source_row_ids=member['source_row_ids']))
        db.flush()
        create_or_update_pattern_cases(db,pattern,user.id)
    # Additional asset-class patterns use the same governance, audit, and privacy gates.
    already={m['investor_id'] for m in finding['members']} if finding['matched'] else set()
    secondary=detect_general_peer_clusters(investors,holdings,excluded_ids=already)
    for result in secondary:
        other=DetectedPattern(run_id=run.id,organization_id=user.organization_id,rule_id=result['rule_id'],
              rule_version=RULE_VERSION,snapshot_date=date.fromisoformat(result['as_of_date']),
              member_count=result['member_count'],advisor_count=result['advisor_count'],
              recorded_value_total=Decimal(result['recorded_value_total']),evidence_summary=result['reason'])
        db.add(other);db.flush()
        for member in result['members']:
            db.add(PatternMember(pattern_id=other.id,investor_id=member['investor_id'],
                advisor_id=member['advisor_id'],equity_pct=Decimal(member['equity_pct']),
                fixed_deposit_pct=Decimal(member['fixed_deposit_pct']),
                recorded_value=Decimal(member['recorded_value']),evidence_source_row_ids=member['source_row_ids']))
        db.flush()
        create_or_update_pattern_cases(db,other,user.id)
        run.matched_count+=result['member_count']
    db.add(AuditEvent(organization_id=user.organization_id,actor_id=user.id,action='PATTERN_SCAN',
        entity_type='PatternRun',entity_id=run.id,detail=json.dumps({'rule':PATTERN_RULE,'matches':run.matched_count,'as_of':finding['as_of_date']})))
    db.commit()
    return {'run_id':run.id,'as_of_date':finding['as_of_date'],'matched':finding['matched'],
            'pattern_id':pattern.id if pattern else None,
            'member_count':finding['member_count'] if finding['matched'] else 0,
            'advisor_count':finding['advisor_count'] if finding['matched'] else 0,
            'recorded_value_total':finding['recorded_value_total'] if finding['matched'] else '0.00',
            'additional_pattern_count':len(secondary),'coverage':finding['coverage'],
            'message':'Historical peer-comparison review signals, not evidence of unsuitable advice. New scans create an auditable run.'}


@router.get('/patterns')
def list_patterns(user:User=Depends(current_user),db:Session=Depends(get_db)):
    latest=db.scalar(select(PatternRun).where(PatternRun.organization_id==user.organization_id)
                     .order_by(PatternRun.created_at.desc(),PatternRun.id.desc()).limit(1))
    if not latest:return {'items':[],'latest_run':None,'message':'No pattern scan has been run. Use Run pattern scan after validating holdings.'}
    pats=db.scalars(select(DetectedPattern).where(DetectedPattern.run_id==latest.id)).all()
    items=[]
    for p in pats:
        try:
            _,members=allowed_pattern(db,user,p.id)
            items.append(pattern_public(p,members,user))
        except HTTPException:continue
    return {'items':items,'latest_run':{'id':latest.id,'as_of_date':latest.as_of_date.isoformat() if latest.as_of_date else None,
                                       'rule_version':latest.rule_version,'created_at':latest.created_at.isoformat()},
            'message':'All findings are based on dated imported holdings and require advisor verification.'}


@router.get('/patterns/{pattern_id}')
def get_pattern(pattern_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    pat,members=allowed_pattern(db,user,pattern_id)
    return pattern_public(pat,members,user)


@router.get('/insights/behaviour')
def group_behaviour(user:User=Depends(current_user),db:Session=Depends(get_db)):
    """Privacy-preserving organization aggregate; named transaction signals limited to assigned clients."""
    transactions=db.scalars(select(InvestmentTransaction).where(InvestmentTransaction.organization_id==user.organization_id)).all()
    signals=behaviour_signals(transactions)
    assigned={i.id for i in db.scalars(scoped_investors(db,user)).all()}
    detailed=[s for s in signals if s.get('investor_id') in assigned]
    bursts=[{'type':s['type'],'asset_class':s['asset_class'],'week_start':s['week_start'],
             'investor_count':s['investor_count'],'description':s['description']}
             for s in signals if s['type']=='REDEMPTION_BURST']
    return {'assigned_signals':detailed,'organization_bursts':bursts,
            'note':'Unassigned investor identities and source references are withheld.'}


@router.get('/insights/risk-labels')
def risk_labels(user:User=Depends(current_user),db:Session=Depends(get_db)):
    """Aggregate diagnostic only, with assigned-client drilldown."""
    from statistics import median
    investors=db.scalars(select(Investor).where(Investor.organization_id==user.organization_id)).all()
    holdings=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id)).all()
    by_i={i.id:[] for i in investors}
    for h in holdings:by_i[h.investor_id].append(h)
    groups={}
    for inv in investors:
        a=allocation_for_holdings(by_i[inv.id])
        if a['status']=='VALID' and a['equity_pct'] is not None:
            groups.setdefault((inv.risk_profile or '').strip().lower(),[]).append((inv.id,Decimal(a['equity_pct'])))
    medians={risk:Decimal(str(median([p for _,p in rows]))) for risk,rows in groups.items() if len(rows)>=3}
    needed=('conservative','moderate','aggressive')
    ordered=all(k in medians for k in needed) and medians['conservative']<=medians['moderate']<=medians['aggressive']
    assigned={i.id for i in db.scalars(scoped_investors(db,user)).all()}
    flags=[]
    if not ordered and all(k in medians for k in needed):
        for risk,rows in groups.items():
            if risk=='conservative' and medians['conservative']>medians['moderate']:
                flags += [id for id,pct in rows if id in assigned and pct>medians['moderate']]
    return {'profile_median_equity_pct':{k:money(v) for k,v in medians.items()},
        'expected_risk_order_observed':ordered if all(k in medians for k in needed) else None,
        'assigned_review_candidates':sorted(flags),
        'note':'Source risk labels and holdings exposures are descriptive. A median ordering inversion is a data/mandate verification prompt, not a verified client risk violation.'}

@router.get('/insights/long-tail')
def long_tail(user:User=Depends(current_user),db:Session=Depends(get_db)):
    """Book-wide anonymous rank totals, own clients only in detail."""
    investors=db.scalars(select(Investor).where(Investor.organization_id==user.organization_id)).all()
    holdings=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id)).all()
    grouped={i.id:[] for i in investors}
    for h in holdings:grouped[h.investor_id].append(h)
    assets={iid:Decimal(allocation_for_holdings(rows)['total_value'] or '0') for iid,rows in grouped.items()}
    ranks={iid:idx for idx,(iid,_) in enumerate(sorted(assets.items(),key=lambda x:(-x[1],x[0])),1)}
    current=db.scalars(select(AttentionCase).where(AttentionCase.organization_id==user.organization_id,
         AttentionCase.status!='RESOLVED',AttentionCase.superseded_by_id.is_(None))).all()
    flagged={c.investor_id for c in current}
    financial={c.investor_id for c in current if c.priority!='V_VERIFY'}
    verification={c.investor_id for c in current if c.priority=='V_VERIFY'}
    assigned={i.id for i in db.scalars(scoped_investors(db,user)).all()}
    return {'investors_ranked':len(ranks),'active_flagged_investors':len(flagged),
       'portfolio_review_investors':len(financial),'verification_investors':len(verification),
       'portfolio_reviews_in_top_eight':sum(ranks[i]<=8 for i in financial if i in ranks),
       'portfolio_reviews_in_top_twenty':sum(ranks[i]<=20 for i in financial if i in ranks),
       'portfolio_reviews_outside_top_twenty':sum(ranks[i]>20 for i in financial if i in ranks),
       'flagged_in_top_eight':sum(ranks[i]<=8 for i in flagged if i in ranks),
       'flagged_outside_top_twenty':sum(ranks[i]>20 for i in flagged if i in ranks),
       'assigned_flagged_ranks':[{'investor_id':i,'rank_by_recorded_holdings':ranks[i]}
                     for i in sorted(flagged & assigned) if i in ranks],
       'note':'Ranking by recorded total holdings, not investment performance, loss, or revenue. Only assigned client IDs are disclosed.'}


@router.get('/investors/{investor_id}/goal-plan')
def get_goal_plan(investor_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    from app.models import GoalPlan
    investor_scope(db,user,investor_id)
    plan=db.scalar(select(GoalPlan).where(GoalPlan.organization_id==user.organization_id,GoalPlan.investor_id==investor_id))
    return {'plan':None if not plan else {'principal':money(plan.principal),'monthly_contribution':money(plan.monthly_contribution),
        'as_of_date':plan.as_of_date.isoformat(),'annual_return_assumptions_pct':plan.annual_rates,'updated_at':plan.updated_at.isoformat()}}


@router.put('/investors/{investor_id}/goal-plan')
def save_goal_plan(investor_id:str,payload:ScenarioInput,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    from app.models import GoalPlan
    from app.models.entities import utcnow
    require_same_origin(request)
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Assigned advisor required')
    investor_scope(db,user,investor_id)
    project_goal(investor_id,payload,request,user,db)
    plan=db.scalar(select(GoalPlan).where(GoalPlan.organization_id==user.organization_id,GoalPlan.investor_id==investor_id))
    if not plan:
        plan=GoalPlan(organization_id=user.organization_id,investor_id=investor_id,advisor_id=user.id)
        db.add(plan)
    plan.principal=payload.principal;plan.monthly_contribution=payload.monthly_contribution;plan.as_of_date=payload.as_of_date
    plan.annual_rates=[str(x) for x in payload.annual_return_assumptions_pct];plan.updated_at=utcnow()
    db.add(AuditEvent(organization_id=user.organization_id,actor_id=user.id,action='GOAL_PLAN_SAVED',entity_type='Investor',entity_id=investor_id))
    db.commit()
    return get_goal_plan(investor_id,user,db)
