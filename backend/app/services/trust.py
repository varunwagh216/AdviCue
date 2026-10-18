"""Conservative source-date inference and transaction-field trust checks.

Ambiguous strings are never silently 'verified'. Only strong dated-SIP recurrence
may label them inferred; all others are quarantined from date-sensitive signals.
"""
from __future__ import annotations
from collections import Counter,defaultdict
from datetime import date
from decimal import Decimal
import re

DATE_TEXT=re.compile(r'^(\d{2})[-/](\d{2})[-/](\d{4})$')

def date_classification(value, *, investor_id=None, expected_days=None):
    if value is None:return 'MISSING'
    if isinstance(value,date):return 'EXACT_ISO_OR_EXCEL'
    raw=str(value).strip()
    match=DATE_TEXT.fullmatch(raw)
    if not match:return 'EXACT_ISO_OR_EXCEL' if re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw) else 'UNRECOGNIZED'
    day,month,year=map(int,match.groups())
    if day>12 or month>12 or day==month:return 'EXPLICIT_OR_IDENTICAL_DAY_FIRST'
    first=set(expected_days or ())
    # Day-of-month recurrence supplies only a provisional inference, never verification.
    if len(first) and day in first and month not in first:return 'INFERRED_DAY_FIRST'
    return 'QUARANTINED_AMBIGUOUS'


def sip_recurrence_days(rows):
    """Infer normal SIP days from EXPLICIT ISO source dates (not from ambiguous strings)."""
    observations=defaultdict(list)
    for row in rows:
        obj=row.raw_data
        if (obj.get('type') or '').strip().lower()!='sip':continue
        raw=str(obj.get('date') or '')
        if not re.fullmatch(r'\d{4}-\d{2}-\d{2}',raw):continue
        try:day=date.fromisoformat(raw).day
        except ValueError:continue
        observations[obj.get('investor_id')].append(day)
    result={}
    for investor,days in observations.items():
        counts=Counter(days)
        common=max(counts.values()) if counts else 0
        if common>=2:result[investor]={day for day,n in counts.items() if n==common}
    return result


def transaction_unit_quality(normalized):
    if any(normalized.get(k) is None for k in ('units','price_per_unit','amount')):return 'UNKNOWN'
    expected=Decimal(str(normalized['units']))*Decimal(str(normalized['price_per_unit']))
    amount=Decimal(str(normalized['amount']))
    if abs(expected-amount)<=max(Decimal('2'),abs(amount)*Decimal('.005')):return 'MATCHED'
    return 'UNRELIABLE_AMOUNT_AUTHORITATIVE' if str(normalized.get('type') or '').strip().lower()=='sip' else 'MISMATCH'
