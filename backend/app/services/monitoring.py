"""Independent per-client review rules. No suitability conclusions or automatic closure."""
from datetime import date, timedelta
from decimal import Decimal as D
from hashlib import sha256
import json
from datetime import datetime,timezone
from uuid import uuid4
from sqlalchemy import select
from app.models import Investor,Holding,AttentionCase,AdviceRecord,FollowUpTask,GoalPlan,InvestmentTransaction,AuditEvent,ReviewEvidence,MonitoringState,AdviceOutcomeReview
from app.engines.financial import allocation_for_holdings,goal_scenarios,months_remaining
from app.engines.evidence import PerformanceEvidence,reconcile


def client_signals(inv,holdings,tasks,advice,plan,transactions,mandate,performance,*,today=None,reviewed_advice_ids=()):
    today=today or date.today();signals=[];a=allocation_for_holdings(holdings)
    def add(code,title,band,reason,refs=None,key=None):signals.append({'rule_id':code,'title':title,'priority':band,'reason':reason,'source_row_ids':refs or [],'change_key':key if key is not None else [reason]})
    observed=date.fromisoformat(a['as_of_date']) if a.get('as_of_date') else None
    if not observed or (today-observed).days>45 or observed>today or a['status']=='ZERO_VALUATION':
        add('STALE_VALUATION','Refresh portfolio evidence','V_VERIFY','Portfolio evidence is missing, older than 45 days, zero-valued or future-dated. Refresh before drawing financial conclusions.',a.get('source_row_ids'),key=[a.get('as_of_date'),a['status']])
    overdue=[t for t in tasks if t.status in ('OPEN','IN_PROGRESS') and t.due_date<today]
    if overdue:add('OVERDUE_COMMITMENT','Follow up overdue commitments','P1',f'{len(overdue)} open follow-up tasks are overdue.',key=sorted((str(getattr(t,'id','')),t.due_date.isoformat()) for t in overdue))
    due=[x for x in advice if x.status=='APPROVED' and x.review_date and x.review_date<=today and x.id not in reviewed_advice_ids]
    if due:add('ADVICE_REVIEW_DUE','Review an approved recommendation','P2',f'{len(due)} approved advice records reached their review date; check subsequent evidence.',key=sorted((x.id,x.review_date.isoformat()) for x in due))
    if mandate and observed and a['status']=='VALID' and 0<=(today-observed).days<=45:
        effective=date.fromisoformat(mandate['effective_from']);until=date.fromisoformat(mandate['effective_to'])
        if effective<=observed<=today<=until:
            weights={c['asset_class'].casefold():D(c['weight_pct']) for c in a['asset_classes']}
            for b in mandate['bands']:
                value=weights.get(b['asset_class'].casefold(),D(0))
                if not D(b['min_pct'])<=value<=D(b['max_pct']):
                    add('APPROVED_TARGET_DRIFT','Check allocation against the approved mandate','P1',('Illustrative mandate: ' if mandate.get('illustrative') else '')+f"{b['asset_class']} is {value}% versus the recorded approved range {b['min_pct']}–{b['max_pct']}%. Confirm current context before any recommendation.",a['source_row_ids'],key=[b,str(value.quantize(D('1'))),mandate.get('source_reference')])
        else:add('MANDATE_REVALIDATION','Revalidate the allocation mandate','V_VERIFY','The approved mandate does not cover the current date and valuation date.')
    if plan and inv.goal_target_date and inv.goal_target_amount:
        n=months_remaining(plan.as_of_date,inv.goal_target_date)
        if 0<n<=1200:
            if (today-plan.as_of_date).days>30 or plan.as_of_date>today:
                add('GOAL_INPUT_REFRESH','Confirm goal-plan balances','V_VERIFY','Goal funds are dated more than 30 days ago or in the future. Confirm inputs before a new assessment.',key=[plan.as_of_date.isoformat()])
            else:
                scenarios=goal_scenarios(principal=plan.principal,monthly_contribution=plan.monthly_contribution,target_amount=inv.goal_target_amount,months=n,annual_rates=[D(x)/100 for x in plan.annual_rates])
                if all(D(s['goal_gap'])<0 for s in scenarios):add('GOAL_FUNDING_GAP','Review the recorded goal funding plan','P2','All scenarios from the advisor-saved plan date fall below the target. This is an assumption-based scenario, not a current balance or forecast.',key=[str(plan.principal),str(plan.monthly_contribution),plan.annual_rates,str(inv.goal_target_amount),inv.goal_target_date.isoformat(),n])
    eligible=[t for t in transactions if not t.possible_duplicate and t.date_confidence!='QUARANTINED_AMBIGUOUS' and 0<=(today-t.date).days<=30]
    amount=sum((D(t.amount) for t in eligible if t.type.lower()=='redemption'),D(0))
    value=D(a.get('total_value') or 0)
    if observed and 0<=(today-observed).days<=45 and value>0 and amount/value>=D('.20'):
        refs=[t.source_row_id for t in eligible if t.type.lower()=='redemption']
        add('RECENT_REDEMPTION','Discuss a material recorded withdrawal','P2','Recorded redemptions in the last 30 days exceed 20% of the latest recorded holdings. Confirm purpose and completeness; no psychological motive is inferred.',refs,key=sorted((str(getattr(t,'external_transaction_id',t.source_row_id)),str(t.amount),t.date.isoformat()) for t in eligible if t.type.lower()=='redemption'))
    if performance:
        result=reconcile(PerformanceEvidence.model_validate(performance))
        if (today-date.fromisoformat(result['end_date'])).days<=45 and D(result['active_return_pp'])<=-3:
            add('RECONCILED_BENCHMARK_LAG','Review the source-reviewed benchmark gap','P2',('Illustrative performance: ' if performance.get('illustrative') else '')+f"Reconciled TWR is {result['active_return_pp']} pp below the reviewed benchmark over {result['start_date']} to {result['end_date']}. This does not establish a cause or a suitability finding.",key=performance)
    return signals


def refresh_clients(db,user):
    q=select(Investor).where(Investor.organization_id==user.organization_id)
    if user.role=='ADVISOR':q=q.where(Investor.advisor_id==user.id)
    clients=db.scalars(q).all();ids=[i.id for i in clients];today=date.today()
    def grouped(model):
        rows=db.scalars(select(model).where(model.organization_id==user.organization_id,model.investor_id.in_(ids))).all() if ids else []
        result={iid:[] for iid in ids}
        for row in rows:result[row.investor_id].append(row)
        return result
    held=grouped(Holding);tasks=grouped(FollowUpTask);advice=grouped(AdviceRecord);plans=grouped(GoalPlan);tx=grouped(InvestmentTransaction);evidence=grouped(ReviewEvidence)
    reviews=grouped(AdviceOutcomeReview)
    states={(s.investor_id,s.stream):s for s in db.scalars(select(MonitoringState).where(MonitoringState.organization_id==user.organization_id,MonitoringState.investor_id.in_(ids))).all()}
    previous=grouped(AttentionCase)
    changed=0;matched=set();summary=[];unchanged=0
    for inv in clients:
        approved=[e for e in evidence[inv.id] if e.status=='APPROVED']
        def newest(kind):
            rows=[e for e in approved if e.kind==kind]
            return max(rows,key=lambda x:(x.approved_at,x.id)).payload if rows else None
        from app.engines.advice_evidence import objective_review
        reviewed=set()
        for a in advice[inv.id]:
            saved=[r for r in reviews[inv.id] if r.advice_id==a.id and r.result.get('status') in ('OBJECTIVE_MET','OBJECTIVE_NOT_MET')]
            if saved:
                last=max(saved,key=lambda r:(r.created_at,r.id))
                current=objective_review(a,held[inv.id],approved,today=today)
                if current.get('evidence_sha256')==last.result.get('evidence_sha256') and current.get('source_row_ids')==last.result.get('source_row_ids'):reviewed.add(a.id)
        signals=client_signals(inv,held[inv.id],tasks[inv.id],advice[inv.id],plans[inv.id][0] if plans[inv.id] else None,tx[inv.id],newest('MANDATE'),newest('PERFORMANCE'),today=today,reviewed_advice_ids=reviewed)
        if signals:matched.add(inv.id)
        for stream in (False,True):
            subset=[s for s in signals if (s['priority']=='V_VERIFY')==stream]
            rule='MON_VERIFY' if stream else 'MON_CLIENT_REVIEW'
            state=states.get((inv.id,rule))
            if state:state.checked_at=datetime.now(timezone.utc)
            if not subset:
                if state:state.active=False
                continue
            priority='V_VERIFY' if stream else ('P1' if any(s['priority']=='P1' for s in subset) else 'P2')
            fingerprint=sha256(json.dumps(sorted([(s['rule_id'],s['priority'],s['change_key']) for s in subset],key=lambda x:json.dumps(x,sort_keys=True,default=str)),sort_keys=True,default=str).encode()).hexdigest()
            refs=sorted({ref for s in subset for ref in s['source_row_ids']})
            reason='\n'.join(f"{s['title']}: {s['reason']}" for s in subset)
            same=bool(state and state.active and state.fingerprint==fingerprint)
            row=db.get(AttentionCase,state.current_case_id) if same and state.current_case_id else None
            if row:unchanged+=1
            else:
                row=AttentionCase(organization_id=user.organization_id,investor_id=inv.id,advisor_id=inv.advisor_id,rule_id=rule+'_'+uuid4().hex[:16],rule_version='6.0',source_date=today,priority=priority,status='NEEDS_DATA' if stream else 'OPEN',title=subset[0]['title'],reason=reason,suggested_action='Review dated evidence, record the agreed next step and resolve with a reason. Unchanged conditions will not reopen automatically.',evidence_source_row_ids=refs)
                db.add(row);db.flush();changed+=1
                older=[c for c in previous[inv.id] if c.rule_id.startswith(rule) and c.superseded_by_id is None]
                for old in older:old.superseded_by_id=row.id
            if not state:
                state=MonitoringState(organization_id=user.organization_id,investor_id=inv.id,stream=rule);db.add(state)
            state.fingerprint=fingerprint;state.active=True;state.current_case_id=row.id;state.checked_at=datetime.now(timezone.utc)
            summary.append({'investor_id':inv.id,'case_id':row.id,'priority':priority,'rules':[s['rule_id'] for s in subset]})
    db.add(AuditEvent(organization_id=user.organization_id,actor_id=user.id,action='INDEPENDENT_MONITORING_REFRESH',entity_type='Investor',entity_id='ASSIGNED_BOOK',detail=f'Checked {len(clients)} assigned clients; matched {len(matched)}; created {changed} cases.'))
    db.commit();return {'clients_checked':len(clients),'clients_with_signals':len(matched),'cases_created':changed,'unchanged_conditions':unchanged,'items':summary,'rules_version':'6.0'}
