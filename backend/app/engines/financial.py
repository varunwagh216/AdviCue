"""Phase 3 deterministic finance: no LLM-produced numbers and no implied investment returns."""
from __future__ import annotations
from collections import defaultdict
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

EQUITY_CLASSES = frozenset({'Direct Equity', 'Equity Mutual Fund', 'International Equity Fund'})
FD_CLASSES = frozenset({'Fixed Deposit'})
D = Decimal
CENT = D('0.01')


def money(value: Decimal) -> str:
    return str(value.quantize(CENT, rounding=ROUND_HALF_UP))


def percentage(part: Decimal, total: Decimal) -> str | None:
    if total <= 0:
        return None
    return str((D('100') * part / total).quantize(D('0.01'), rounding=ROUND_HALF_UP))


def allocation_for_holdings(holdings: list) -> dict:
    """All rows must belong to one investor and same valuation date.

    Prevents a false allocation resulting from mixing historical snapshot dates.
    Keeps source row IDs so the client can inspect evidence for every number.
    """
    if not holdings:
        return {'status':'NO_HOLDINGS','as_of_date':None,'total_value':None,'currency':'INR',
                'asset_classes':[],'equity_pct':None,'fixed_deposit_pct':None,'source_row_ids':[],
                'explanation':'No validated holdings available.'}
    latest = max(h.as_of_date for h in holdings)
    rows = [h for h in holdings if h.as_of_date == latest]
    groups = defaultdict(lambda: {'value': D('0'), 'source_row_ids': []})
    for h in rows:
        value = D(h.current_value)
        if value < 0:
            raise ValueError('Negative holdings cannot be used in allocation')
        groups[h.asset_class]['value'] += value
        groups[h.asset_class]['source_row_ids'].append(h.source_row_id)
    total = sum((v['value'] for v in groups.values()), D('0'))
    classes = [{'asset_class':name,'value':money(info['value']),
                'weight_pct':percentage(info['value'],total),
                'source_row_ids':sorted(info['source_row_ids'])}
               for name,info in sorted(groups.items())]
    eq = sum((info['value'] for key,info in groups.items() if key in EQUITY_CLASSES),D('0'))
    fd = sum((info['value'] for key,info in groups.items() if key in FD_CLASSES),D('0'))
    return {'status':'VALID' if total > 0 else 'ZERO_VALUATION','as_of_date':latest.isoformat(),
            'total_value':money(total),'currency':'INR', 'asset_classes':classes,
            'equity_pct':percentage(eq,total),'fixed_deposit_pct':percentage(fd,total),
            'source_row_ids':sorted(h.source_row_id for h in rows),
            'explanation':'Recorded, same-date holdings allocation; not a suitability assessment.'}


def recorded_value_change(start: Decimal, end: Decimal) -> str | None:
    """Not a portfolio return: external flows can affect beginning/end balances."""
    if start <= 0:
        return None
    return percentage(end - start, start)


def xirr(flows: list[tuple[date, Decimal]], *, tolerance=D('0.00000001')) -> Decimal:
    """Calculate annualized XIRR from complete external cash flows and terminal valuation.

    A single sign change isn't sufficient: require one unique root in the supported
    economic range (-99.99%, +1000% annualized); otherwise refuse a misleading rate.
    External-flow classification and terminal value must be validated by the caller.
    """
    if len(flows) < 2 or not any(v < 0 for _,v in flows) or not any(v > 0 for _,v in flows):
        raise ValueError('XIRR needs dated inflows and outflows')
    flows = sorted(flows, key=lambda row: row[0])
    origin = flows[0][0]
    years = [D((day-origin).days)/D('365') for day,_ in flows]
    if max(years) <= 0:
        raise ValueError('XIRR needs different cash-flow dates')
    def npv(rate: D) -> D:
        base = D('1')+rate
        return sum((value / (base ** t) for (_,value),t in zip(flows,years)), D('0'))
    # Scan for multiple roots before bisection; avoids choosing arbitrary rates.
    candidates=[D('-0.9999'),D('-0.99'),D('-0.9'),D('-0.5'),D('-0.2'),D('0'),D('0.1'),D('0.2'),D('0.5'),D('1'),D('2'),D('5'),D('10')]
    brackets=[]
    prev=candidates[0]; prev_value=npv(prev)
    for rate in candidates[1:]:
        value=npv(rate)
        if prev_value == 0:
            brackets.append((prev,prev))
        elif (prev_value < 0 < value) or (prev_value > 0 > value):
            brackets.append((prev,rate))
        prev,prev_value=rate,value
    if prev_value==0:
        brackets.append((prev,prev))
    if len(brackets)!=1:
        raise ValueError('XIRR has no unique validated root in the supported range')
    lo,hi=brackets[0]
    if lo==hi:return lo
    lo_sign=npv(lo)>0
    for _ in range(160):
        mid=(lo+hi)/2
        val=npv(mid)
        if hi-lo < tolerance:return mid
        if (val > 0)==lo_sign:lo=mid
        else:hi=mid
    return (lo+hi)/2


def linked_twr(returns: list[Decimal]) -> Decimal:
    """Only call with verified subperiod returns around all external cash flows."""
    if not returns:raise ValueError('No verified subperiods')
    accum=D('1')
    for r in returns:
        if r < -1:raise ValueError('Subperiod return below -100%')
        accum *= D('1')+r
    return accum-D('1')


def goal_scenarios(*, principal: Decimal, monthly_contribution: Decimal,
                   target_amount: Decimal, months: int, annual_rates: list[Decimal]) -> list[dict]:
    """Scenario-based FV of an explicitly assigned principal with END-month payments.

    Input rates are annual effective decimals (0.08 means 8%). Never probabilities.
    """
    if principal < 0 or monthly_contribution < 0 or target_amount <= 0:
        raise ValueError('Principal/contribution must be nonnegative; target must be positive')
    if months < 1 or months > 1200:
        raise ValueError('Goal horizon must be 1 to 1200 months')
    if not annual_rates or len(annual_rates)>5 or any(r <= D('-1') or r > D('1') for r in annual_rates):
        raise ValueError('Supply 1–5 effective annual assumptions above -100% and at most +100%')
    out=[]
    for annual in annual_rates:
        rate=(D('1')+annual)**(D('1')/D('12'))-D('1')
        growth=(D('1')+rate)**months
        fv=principal*growth + (monthly_contribution * (growth-D('1'))/rate if rate != 0 else monthly_contribution*months)
        out.append({'annual_assumption_pct':str((annual*100).quantize(D('0.01'))),
                    'projected_value':money(fv), 'goal_gap':money(fv-target_amount),
                    'meets_target_under_assumption':fv>=target_amount})
    return out


def months_remaining(as_of: date, target: date) -> int:
    """Whole remaining contribution months, rounding incomplete month up."""
    if target<=as_of:return 0
    months=(target.year-as_of.year)*12 + (target.month-as_of.month)
    if target.day > as_of.day:months += 1
    return months
