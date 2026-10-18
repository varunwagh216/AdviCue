"""Phase 4 explainable, cohort-based detection over validated same-date holdings."""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from decimal import Decimal
from statistics import median
import re
from app.engines.financial import allocation_for_holdings, money

PATTERN_RULE = 'PAT_PEER_EQ_FD_DEVIATION'
RULE_VERSION = '4.0'
MIN_GROUP_SIZE = 3


def comparable_date(holdings):
    coverage=defaultdict(set)
    for h in holdings:coverage[h.as_of_date].add(h.investor_id)
    return max(coverage,key=lambda d:(len(coverage[d]),d),default=None)


def cohort_coverage(investors, holdings, day):
    included={h.investor_id for h in holdings if h.as_of_date==day}
    newer={h.investor_id for h in holdings if day and h.as_of_date>day}
    return {'policy':'Largest same-date coverage; newest date breaks ties',
            'included_count':len(included),'excluded_count':len({i.id for i in investors}-included),
            'newer_snapshot_count':len(newer),'comparison_date':day.isoformat() if day else None}



def detect_low_equity_fd(investors:list, holdings:list, *, as_of:date|None=None,
                         excluded_row_ids:set[str]|None=None, comparisons:dict|None=None) -> dict:
    excluded_row_ids=excluded_row_ids or set()
    by_investor=defaultdict(list)
    for row in holdings:
        if row.source_row_id not in excluded_row_ids and (as_of is None or row.as_of_date <= as_of):
            by_investor[row.investor_id].append(row)
    cohort_date=comparable_date([h for rows in by_investor.values() for h in rows])
    observations=[]
    for inv in investors:
        rows=[h for h in by_investor[inv.id] if h.as_of_date==cohort_date]
        a=allocation_for_holdings(rows)
        if a['status']!='VALID':continue
        observations.append((inv,a))
    members=[]
    # Cohort-based, data-relative deviation. No sample-specific fixed 1%/50% thresholds.
    for inv,a in observations:
        profile=(inv.risk_profile or '').strip().lower()
        cohort=[p for i,p in observations if (i.risk_profile or '').strip().lower()==profile]
        if len(cohort)<MIN_GROUP_SIZE+1:continue
        # Leave-one-out median and median absolute deviation, with meaningful floors.
        others=[p for i,p in observations if i.id!=inv.id and (i.risk_profile or '').strip().lower()==profile]
        eq=[Decimal(p['equity_pct']) for p in others]
        fd=[Decimal(p['fixed_deposit_pct']) for p in others]
        eq_mid=Decimal(str(median(eq)));fd_mid=Decimal(str(median(fd)))
        eq_mad=Decimal(str(median(abs(x-eq_mid) for x in eq)))
        fd_mad=Decimal(str(median(abs(x-fd_mid) for x in fd)))
        equity_gap=eq_mid-Decimal(a['equity_pct'])
        deposit_gap=Decimal(a['fixed_deposit_pct'])-fd_mid
        unusual=equity_gap>=max(Decimal('10'),eq_mad*3) and deposit_gap>=max(Decimal('15'),fd_mad*3)
        # When a small imported book contains one identical cohort and no
        # contrasting peers, retain a shared-exposure review signal, explicitly
        # without claiming it is statistically unusual.
        common_exposure=(len(cohort)<=5 and len({(p['equity_pct'],p['fixed_deposit_pct']) for p in cohort})==1
                         and Decimal(a['fixed_deposit_pct'])>=Decimal('50')
                         and Decimal(a['fixed_deposit_pct'])>Decimal(a['equity_pct']))
        if not (unusual or common_exposure):continue
        # Optional persistence gate, never invented when reported history is absent.
        comparison=(comparisons or {}).get(inv.id)
        if comparison and comparison.get('observed_months',0)>=6:
            if comparison['negative_months']/comparison['observed_months'] < .60:continue
        members.append({'investor_id':inv.id,'advisor_id':inv.advisor_id,'advisor_code':inv.source_advisor_code,
                        'equity_pct':a['equity_pct'],'fixed_deposit_pct':a['fixed_deposit_pct'],
                        'recorded_value':a['total_value'],'source_row_ids':a['source_row_ids']})
    members.sort(key=lambda x:x['investor_id'])
    return {'coverage':cohort_coverage(investors,[h for rows in by_investor.values() for h in rows],cohort_date),
            'matched':len(members)>=MIN_GROUP_SIZE,'rule_id':PATTERN_RULE,'rule_version':RULE_VERSION,
            'as_of_date':cohort_date.isoformat() if cohort_date else None,
            'member_count':len(members),'advisor_count':len({m['advisor_code'] or m['advisor_id'] for m in members}),
            'recorded_value_total':money(sum((Decimal(m['recorded_value']) for m in members),Decimal('0'))),
            'members':members,
            'reason':'Same-date investor group with unusually low equity and unusually high fixed deposits versus leave-one-out peers of the same risk profile (median/MAD with minimum spread); source-reported persistence is checked when available.',
            'interpretation':'Review signal only; not evidence of unsuitable advice, a mandate breach, or investment loss.'}


def detect_general_peer_clusters(investors:list,holdings:list,*,as_of:date|None=None,
                                 excluded_ids:set[str]|None=None)->list[dict]:
    """Explore any asset class, either direction, relative to risk-matched peers.

    Preserve a stable pattern key and only create groups where 3+ independent
    investors share the same deviation. Avoid duplicating the main FD/equity cluster.
    """
    excluded_ids=excluded_ids or set()
    by_investor=defaultdict(list)
    for h in holdings:
        if as_of is None or h.as_of_date<=as_of:
            by_investor[h.investor_id].append(h)
    date_latest=comparable_date([h for rows in by_investor.values() for h in rows])
    if date_latest is None:return []
    obs=[]
    for inv in investors:
        a=allocation_for_holdings([h for h in by_investor[inv.id] if h.as_of_date==date_latest])
        if a['status']=='VALID':
            obs.append((inv,a,{r['asset_class']:Decimal(r['weight_pct']) for r in a['asset_classes']}))
    candidates=defaultdict(list)
    for inv,a,weights in obs:
        cohort=[(peer,alloc,w) for peer,alloc,w in obs if peer.id!=inv.id and peer.risk_profile==inv.risk_profile]
        if len(cohort)<5:continue
        classes=set(weights)
        for _,_,w in cohort:classes.update(w)
        for cls in classes:
            values=[w.get(cls,Decimal('0')) for _,_,w in cohort]
            mid=Decimal(str(median(values)))
            mad=Decimal(str(median([abs(v-mid) for v in values])))
            delta=weights.get(cls,Decimal('0'))-mid
            if abs(delta)<max(Decimal('15'),mad*3):continue
            direction='HIGH' if delta>0 else 'LOW'
            signature=(inv.risk_profile or 'UNSPECIFIED',cls,direction)
            candidates[signature].append({'investor_id':inv.id,'advisor_id':inv.advisor_id,
                'advisor_code':inv.source_advisor_code,'equity_pct':a['equity_pct'],
                'fixed_deposit_pct':a['fixed_deposit_pct'],'recorded_value':a['total_value'],
                'source_row_ids':a['source_row_ids']})
    groups=[]
    for (profile,klass,direction),members in sorted(candidates.items()):
        members=[m for m in members if m['investor_id'] not in excluded_ids]
        if len(members)<MIN_GROUP_SIZE:continue
        # One canonical signal for each cohort/class/direction.
        import hashlib
        signature_hash=hashlib.sha256(f'{profile}|{klass}|{direction}'.encode()).hexdigest()[:10]
        key='PAT_PEER_'+('HI' if direction=='HIGH' else 'LO')+'_'+re.sub(r'[^A-Z0-9]','_',klass.upper())[:24]+'_'+signature_hash
        groups.append({'matched':True,'rule_id':key,'rule_version':RULE_VERSION,
              'as_of_date':date_latest.isoformat(),'member_count':len(members),
              'advisor_count':len({m['advisor_code'] or m['advisor_id'] for m in members}),
              'recorded_value_total':money(sum((Decimal(m['recorded_value']) for m in members),Decimal('0'))),
              'members':sorted(members,key=lambda m:m['investor_id']),
              'reason':f'{profile} clients share unusually {direction.lower()} {klass} exposure versus leave-one-out risk-matched peer medians; verify mandate and source coverage.'})
    return groups
