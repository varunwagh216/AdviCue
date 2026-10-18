"""Deterministic source-reported intelligence; no unverified investment returns.

Reported return columns have not been independently reconstructed from flows.
Peer exposure differences cannot establish causal return attribution.
"""
from __future__ import annotations
from collections import Counter, defaultdict
from datetime import timedelta
from decimal import Decimal, ROUND_HALF_UP
from statistics import median

D=Decimal
TWO=D('0.01')

def rounded(x):
    return str(D(str(x)).quantize(TWO,rounding=ROUND_HALF_UP))

def reported_comparison(snapshots):
    rows=[]
    for snap in sorted(snapshots,key=lambda s:s.snapshot_date):
        p=snap.source_reported_portfolio_return_pct
        b=snap.source_reported_benchmark_return_pct
        if p is None or b is None:continue
        p,b=D(p),D(b)
        rows.append({'date':snap.snapshot_date.isoformat(),'reported_return_pct':rounded(p),
                     'reported_benchmark_pct':rounded(b),'gap_pp':rounded(p-b),
                     'source_row_id':snap.source_row_id})
    if not rows:
        return {'status':'NO_REPORTED_COMPARISON','reason':'Source return/benchmark columns are absent.',
                'months':[],'negative_months':0,'observed_months':0,'sum_monthly_gap_pp':None,
                'last_three_gap_pp':None,'reported_linked_portfolio_pct':None,'reported_linked_benchmark_pct':None,
                'reported_linked_gap_pp':None,'source_row_ids':[]}
    neg=sum(D(row['gap_pp'])<0 for row in rows)
    p_growth=b_growth=D('1')
    for row in rows:
        p_growth*=D('1')+D(row['reported_return_pct'])/100
        b_growth*=D('1')+D(row['reported_benchmark_pct'])/100
    return {'status':'SOURCE_REPORTED_UNVERIFIED','reason':
            'Source-reported percentages compared with source benchmark columns; neither return methodology nor benchmark suitability is independently verified.',
            'months':rows,'negative_months':neg,'observed_months':len(rows),
            'sum_monthly_gap_pp':rounded(sum((D(x['gap_pp']) for x in rows),D('0'))),
            'last_three_gap_pp':rounded(sum((D(x['gap_pp']) for x in rows[-3:]),D('0'))),
            'reported_linked_portfolio_pct':rounded((p_growth-1)*100),
            'reported_linked_benchmark_pct':rounded((b_growth-1)*100),
            'reported_linked_gap_pp':rounded((p_growth-b_growth)*100),
            'source_row_ids':[r['source_row_id'] for r in rows]}


def allocation_peer_explanation(allocation,peer_allocations):
    """Explain allocation exposure only. Never call this financial return attribution."""
    if allocation.get('status')!='VALID':
        return {'status':'NO_ALLOCATION','items':[],'note':'Insufficient same-date holdings.'}
    peers=[p for p in peer_allocations if p.get('status')=='VALID']
    if len(peers)<3:
        return {'status':'INSUFFICIENT_PEERS','items':[],'note':'At least three comparable peer allocations are needed.'}
    def weights(item):return {a['asset_class']:D(a['weight_pct']) for a in item['asset_classes'] if a['weight_pct'] is not None}
    own=weights(allocation)
    peer=[weights(p) for p in peers]
    classes=sorted(set(own).union(*(set(p) for p in peer)))
    items=[]
    for cls in classes:
        cohort=D(str(median([p.get(cls,D('0')) for p in peer])))
        own_pct=own.get(cls,D('0'))
        items.append({'asset_class':cls,'client_weight_pct':rounded(own_pct),
                      'peer_median_weight_pct':rounded(cohort),
                      'weight_difference_pp':rounded(own_pct-cohort)})
    return {'status':'ALLOCATION_ONLY','items':items,
            'note':'Exposure differences versus risk-profile peers, NOT a return attribution. No asset-class total-return series was supplied; the observed benchmark gap remains unattributed.'}


def priority_components(comparison,recorded_value,goal_date=None,as_of=None,data_confidence='SOURCE_REPORTED'):
    """Explainable triage, not suitability or value-at-risk; requires >=6 reported periods."""
    n=comparison.get('observed_months',0)
    if n==0:
        return {'band':'P2','score':0,'components':{'reason':'Allocation-only case, no reported performance'},'explanation':'Review allocation; no benchmark ranking available.'}
    if n<6:
        return {'band':'V_VERIFY','score':0,'components':{'observed_months':n,'reason':'Too few reported comparisons'},
                'explanation':'Verify source performance series before ranking.'}
    gap=abs(min(D(comparison['sum_monthly_gap_pp']),D('0')))
    persistence=D(comparison['negative_months'])/D(n)
    gap_score=35 if gap>=15 else 20 if gap>=7 else 8 if gap>=2 else 0
    persistence_score=35 if persistence>=D('.80') else 22 if persistence>=D('.60') else 10 if persistence>=D('.40') else 0
    amount=D(recorded_value or 0)
    assets_score=15 if amount>=D('1000000') else 10 if amount>=D('400000') else 5 if amount>0 else 0
    soon=bool(goal_date and as_of and 0 <= (goal_date-as_of).days<=365)
    goal_score=10 if soon else 0
    score=gap_score+persistence_score+assets_score+goal_score
    band='P1' if score>=65 else 'P2' if score>=35 else 'P3'
    return {'band':band,'score':score,'components':{
        'summed_negative_gap_pp':rounded(gap),'negative_months':comparison['negative_months'],
        'observed_months':n,'gap_points':gap_score,'persistence_points':persistence_score,
        'assets_points':assets_score,'goal_points':goal_score,'data_confidence':data_confidence},
        'explanation':'Triage based on source-reported benchmark gap, persistence, recorded assets and goal timing; not a verified loss or suitability finding.'}


def behaviour_signals(transactions):
    """Evidence-backed transaction pattern summaries. Exclude later flagged duplicate copies."""
    tx=[t for t in transactions if not t.possible_duplicate and getattr(t,'date_confidence',None)!='QUARANTINED_AMBIGUOUS']
    sip=defaultdict(lambda:{'amount':D('0'),'ids':[],'months':set()})
    redemptions=defaultdict(list)
    by_month=defaultdict(set)
    for t in tx:
        typ=(t.type or '').strip().lower()
        if typ=='sip':
            item=sip[(t.investor_id,t.asset_class)]
            item['amount']+=D(t.amount);item['ids'].append(t.source_row_id)
            item['months'].add(t.date.strftime('%Y-%m'))
            by_month[t.investor_id].add(t.date.strftime('%Y-%m'))
        if typ=='redemption':redemptions[(t.asset_class,t.date)].append(t)
    out=[]
    by_investor=defaultdict(list)
    for (iid,klass),v in sip.items():by_investor[iid].append((klass,v))
    for iid,items in by_investor.items():
        total=sum((v['amount'] for _,v in items),D('0'))
        for klass,v in items:
            if total>0 and v['amount']/total>=D('.95') and len(v['ids'])>=3:
                out.append({'type':'SIP_CONCENTRATION','investor_id':iid,'asset_class':klass,
                            'share_pct':rounded(v['amount']/total*100), 'source_row_ids':v['ids'],
                            'description':'At least 95% of recorded SIP amounts went to a single asset class. Confirm mandate and completeness.'})
    grouped=defaultdict(list)
    for (klass,day),rows in redemptions.items():
        window=day-timedelta(days=day.weekday())
        grouped[(klass,window)].extend(rows)
    for (klass,week),rows in grouped.items():
        investor_ids={r.investor_id for r in rows}
        if len(investor_ids)>=3:
            out.append({'type':'REDEMPTION_BURST','asset_class':klass,'week_start':week.isoformat(),
                        'investor_count':len(investor_ids),'source_row_ids':[r.source_row_id for r in rows],
                        'description':'Several investors redeemed the same asset class during one calendar week; investigate context, not proof of coordinated action.'})
    # Missing months are a documentation gap, NOT proof a mandated SIP was missed.
    for iid,months in by_month.items():
        if len(months)<4:continue
        allmonths=sorted(months)
        start_year,start_month=map(int,allmonths[0].split('-'))
        end_year,end_month=map(int,allmonths[-1].split('-'))
        expected={(year*12+month-1) for year in range(start_year,end_year+1)
                   for month in range(1,13)
                   if start_year*12+start_month-1<=year*12+month-1<=end_year*12+end_month-1}
        observed={int(x[:4])*12+int(x[5:])-1 for x in months}
        missing=sorted(expected-observed)
        if missing:
            out.append({'type':'UNOBSERVED_SIP_MONTHS','investor_id':iid,
                'missing_months':[f'{m//12:04d}-{m%12+1:02d}' for m in missing],
                'source_row_ids':[r.source_row_id for r in tx if r.investor_id==iid and r.type.lower()=='sip'],
                'description':f'{len(missing)} months lack a recorded SIP between the first and last observed SIP; verify source completeness and whether a monthly plan exists.'})
    return out


def advice_outcome(advice,snapshots):
    """Only compare later SOURCE-REPORTED benchmark gaps. No causal attribution to advice."""
    effective=advice.decided_at or advice.submitted_at
    if effective is None or advice.status!='APPROVED':
        return {'status':'NOT_ASSESSABLE','reason':'No finalized advice and start date.'}
    rows=[s for s in snapshots if s.snapshot_date>effective.date()]
    c=reported_comparison(rows)
    if not c['observed_months']:
        return {'status':'NOT_ASSESSABLE','reason':'No post-advice source-reported comparison periods.'}
    previous=reported_comparison([s for s in snapshots if s.snapshot_date<=effective.date()])
    has_baseline=previous['observed_months']>=3
    comparison_change=(rounded(D(c['sum_monthly_gap_pp'])/D(c['observed_months'])-
                       D(previous['sum_monthly_gap_pp'])/D(previous['observed_months']))
                       if has_baseline else None)
    return {'status':'OBSERVATIONAL_ONLY','since':effective.date().isoformat(),
            'reported_comparison':c,'baseline_reported_comparison':previous,
            'reported_mean_monthly_gap_change_pp':comparison_change,
            'execution_verified':False,'mandate_verified':False,
            'reason':'Post-advice source-reported benchmark observations with available pre-advice baseline are NOT evidence that advice caused an outcome. Execution and benchmark suitability remain unverified.'}


def attributable_gap(allocation, peer_exposure, reported, class_return_pct=None):
    """Optional arithmetic exposure attribution with explicit unexplained remainder.

    Contribution of class = (client - peer weight) * class return.
    Returns must be supplied from a separately verified, comparable class-return
    series for the same periods; without it NO causal allocation is claimed.
    """
    gap=reported.get('reported_linked_gap_pp')
    if gap is None:
        return {'status':'NO_REPORTED_GAP','contributions':[],'unexplained_gap_pp':None}
    if not class_return_pct or peer_exposure.get('status')!='ALLOCATION_ONLY':
        return {'status':'NO_CLASS_RETURN_EVIDENCE','contributions':[],
                'unexplained_gap_pp':gap,
                'note':'All of the reported benchmark gap remains unexplained; asset-class return series and aligned benchmark policy are unavailable.'}
    contribution=[]
    for item in peer_exposure['items']:
        cls=item['asset_class']
        if cls not in class_return_pct:
            return {'status':'INCOMPLETE_CLASS_RETURN_EVIDENCE','contributions':[],
                    'unexplained_gap_pp':gap,
                    'note':'Not all asset classes have comparable return series; no attribution shown.'}
        effect=D(item['weight_difference_pp'])*D(str(class_return_pct[cls]))/D('100')
        contribution.append({'asset_class':cls,'contribution_pp':rounded(effect)})
    total=sum((D(x['contribution_pp']) for x in contribution),D('0'))
    return {'status':'PROXY_EXPOSURE_DECOMPOSITION','contributions':contribution,
            'unexplained_gap_pp':rounded(D(gap)-total),
            'note':'Arithmetic exposure proxy only, not a Brinson attribution or proof of causation.'}


def reported_peer_comparison(investor_snapshots, risk_peer_snapshots):
    """Anonymized same-date risk-profile peer median, source-reported only.

    Require three independent peers per date; never return their IDs or rows.
    """
    monthly=defaultdict(list)
    for snap in risk_peer_snapshots:
        r=snap.source_reported_portfolio_return_pct
        if r is not None:monthly[snap.snapshot_date.isoformat()].append((snap.investor_id,D(r)))
    medians={day:D(str(median([value for _,value in rows]))) for day,rows in monthly.items()
             if len({iid for iid,_ in rows})>=3}
    rows=[]
    for s in sorted(investor_snapshots,key=lambda x:x.snapshot_date):
        day=s.snapshot_date.isoformat()
        if s.source_reported_portfolio_return_pct is None or day not in medians:continue
        gap=D(s.source_reported_portfolio_return_pct)-medians[day]
        rows.append({'date':day,'client_source_reported_pct':rounded(s.source_reported_portfolio_return_pct),
                     'risk_peer_median_reported_pct':rounded(medians[day]),'difference_pp':rounded(gap)})
    return {'status':'SOURCE_REPORTED_UNVERIFIED' if rows else 'INSUFFICIENT_PEERS',
            'observed_months':len(rows),'sum_monthly_difference_pp':rounded(sum((D(x['difference_pp']) for x in rows),D('0'))) if rows else None,
            'months':rows,'note':'Peer median from at least three same-risk investors per source month. Unverified reported returns; no unassigned client identifiers shared.'}


def advisor_review_agenda(investor, allocation, comparison, behaviour):
    """Draft questions, never recommendations or suitability findings."""
    agenda=['Confirm the client-approved mandate, investment horizon and immediate liquidity needs.',
            'Verify that source holdings and transaction records are current and complete.']
    if comparison.get('negative_months',0)>=6:
        agenda.append('Ask which benchmark is suitable for the mandate before interpreting recurring source-reported return differences.')
    if allocation.get('fixed_deposit_pct') and D(allocation['fixed_deposit_pct'])>D('30'):
        agenda.append('Discuss the purpose of the recorded fixed-deposit exposure and any capital-preservation preferences.')
    if behaviour:
        agenda.append('Review the documented SIP/redemption pattern and whether it reflects an approved client plan.')
    preferences=getattr(investor,'advisor_preferences',None) or {}
    approved=preferences.get('values',{})
    if approved.get('liquidity_needs'):
        agenda.append('Confirm whether previously approved liquidity preferences are unchanged.')
    draft='Hello, I would like to schedule a portfolio review to confirm your goals, risk preferences and liquidity needs. We will verify your latest records and discuss any concerns before considering recommendations.'
    return {'agenda':agenda,'draft_client_message':draft,
            'note':'Draft conversation starter only; advisor must customize and approve before sending. No investment instruction or performance claim.'}


def check_commitment_against_dated_holdings(check, note, holdings, *, as_of_today=None):
    """Evaluate dated evidence without retroactively crediting late holdings.

    A statement due on a particular date can only be marked kept/broken if
    there is an observation *on that date* after the meeting was approved.
    Earlier observations are an interim trend, not proof of on-time delivery.
    Observations after the due date may be useful for future reviews but do
    not prove the promised deadline was met.
    """
    from datetime import date
    from app.engines.financial import allocation_for_holdings
    today = as_of_today or date.today()
    approved_at = note.approved_at.date() if note.approved_at else None
    if approved_at is None or check.due_date < approved_at:
        return {'status':'NOT_ASSESSABLE','observed_pct':None,'observed_date':None,
                'reason':'Missing meeting approval or invalid due date.'}
    valid=[h for h in holdings if approved_at < h.as_of_date <= check.due_date]
    allocation=allocation_for_holdings(valid)
    observation=allocation.get(check.metric)
    date_recorded=allocation.get('as_of_date')
    if observation is None or not date_recorded:
        status='NOT_ASSESSABLE'
        reason='No post-approval holdings on or before the commitment deadline.'
    else:
        met=(D(observation)>=D(check.target_pct) if check.comparator=='>='
             else D(observation)<=D(check.target_pct))
        if date_recorded==check.due_date.isoformat() and today>=check.due_date:
            status='KEPT' if met else 'BROKEN'
            reason='Observed on the commitment due date. This checks allocation, not client intent or trade execution.'
        elif today<check.due_date:
            status='ON_TRACK' if met else 'DRIFTING'
            reason='Provisional earlier holding; deadline has not yet arrived.'
        else:
            status='NOT_ASSESSABLE'
            reason='Only pre-deadline holdings were recorded; there is no evidence at the due date. Later observations cannot retroactively verify the promise.'
    return {'status':status,'observed_pct':observation,'observed_date':date_recorded,'reason':reason}


def sourced_class_return_proxy(reported, exposure, observations):
    """Audit-friendly *proxy*, not performance causation or Brinson attribution.

    Requires a sourced return for every exposure class in every observed source
    month. Multiply frozen allocation difference by monthly class return; the
    unexplained remainder makes the accounting reconciliation transparent.
    """
    gap=reported.get('sum_monthly_gap_pp')
    if gap is None or exposure.get('status')!='ALLOCATION_ONLY':
        return {'status':'NOT_ASSESSABLE','contributions':[],
                'unexplained_gap_pp':gap,'note':'Portfolio return history or peer exposure unavailable.'}
    months=sorted({row['date'][:7] for row in reported['months']})
    rates={(row.asset_class.casefold(),row.month_date.isoformat()[:7]):D(row.reported_return_pct) for row in observations}
    contributions=[]
    for entry in exposure['items']:
        cls=entry['asset_class']
        missing=[month for month in months if (cls.casefold(),month) not in rates]
        if missing:
            return {'status':'NO_COMPARABLE_CLASS_RETURN_EVIDENCE','contributions':[],
                    'unexplained_gap_pp':gap,'missing_class':cls,'missing_months':missing,
                    'note':'Sourced monthly returns must cover each observed month and all exposure classes before any proxy decomposition can be shown.'}
        monthly=[rates[(cls.casefold(),month)] for month in months]
        weight=D(entry['weight_difference_pp'])/100
        effect=sum((weight*r for r in monthly),D(0))
        sources=[{'month':o.month_date.isoformat()[:7],
                  'source_reference':o.source_reference,'source_file_hash':o.file_sha256}
                 for o in observations if o.asset_class.casefold()==cls.casefold()
                 and o.month_date.isoformat()[:7] in months]
        contributions.append({'asset_class':cls,'proxy_contribution_pp':rounded(effect),
                              'source_references':sources})
    total=sum((D(row['proxy_contribution_pp']) for row in contributions),D(0))
    return {'status':'SOURCED_ALLOCATION_PROXY_NOT_CAUSAL',
            'contributions':contributions,'observed_months':len(months),
            'reported_summed_gap_pp':gap,'unexplained_gap_pp':rounded(D(gap)-total),
            'note':'Uses present allocation differences and third-party monthly class returns as a descriptive proxy against risk peers. Not actual historic client weights, validated return attribution, benchmark suitability, or proof of causality.'}


def evaluate_advice_rule(advice, holdings):
    from datetime import date
    from app.engines.financial import allocation_for_holdings
    rule=advice.outcome_rule
    effective=advice.decided_at
    if advice.status!='APPROVED' or not rule or not effective:
        return {'status':'NOT_ASSESSABLE','reason':'Approved measurable advice and approval date required.','evidence_source_row_ids':[]}
    due=date.fromisoformat(rule['due_date'])
    rows=[h for h in holdings if effective.date()<h.as_of_date<=min(due,date.today())]
    allocation=allocation_for_holdings(rows)
    observed=allocation.get(rule['metric'])
    if observed is None:
        return {'status':'NOT_ASSESSABLE','reason':'No dated post-approval holdings on or before the deadline. Import a later snapshot.','evidence_source_row_ids':[]}
    met=D(observed)>=D(str(rule['target_pct'])) if rule['comparator']=='>=' else D(observed)<=D(str(rule['target_pct']))
    return {'status':'SATISFIED_OBSERVATION' if met else 'NOT_MET_OBSERVATION','observed_pct':observed,
            'observed_date':allocation['as_of_date'],'target_pct':str(rule['target_pct']),'metric':rule['metric'],
            'comparator':rule['comparator'],'due_date':due.isoformat(),
            'deadline_verified':allocation['as_of_date']==due.isoformat() and date.today()>=due,
            'evidence_source_row_ids':allocation['source_row_ids'],
            'reason':'Checks the recorded allocation condition, not trade execution or causation. Deadline fulfilment is verified only with a due-date observation.'}
