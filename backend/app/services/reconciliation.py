"""Non-destructive transaction-to-holdings cross-sheet reconciliation.

Instrument naming is inconsistent in the source; investor + asset class is the
strongest *descriptive* cross-sheet link. This is not a security identifier or
proof that units, transactions, and position balances reconcile.
"""
from __future__ import annotations
from collections import defaultdict
from decimal import Decimal


def reconcile_transactions_holdings(holdings, transactions):
    """Compare investor/class groupings; exclude duplicate copies from aggregate flows.

    Do not silently change the original holdings, transactions, or source rows.
    Quarantined dates can contribute to *undated* amounts but never dated flows.
    """
    groups = defaultdict(lambda: {
        'holding_value': Decimal('0'), 'source_holding_rows': [],
        'contributions': Decimal('0'), 'withdrawals': Decimal('0'),
        'source_transaction_rows': [], 'source_instrument_names': set(),
        'matched_holding_names': set(), 'unverified_date_count': 0,
        'unreliable_sip_units_count': 0,
    })
    for h in holdings:
        g = groups[(h.investor_id, h.asset_class.strip().casefold())]
        g['holding_value'] += Decimal(h.current_value)
        g['source_holding_rows'].append(h.source_row_id)
        g['matched_holding_names'].add(h.instrument_name.strip().casefold())
    all_tx = list(transactions)
    excluded_duplicates = 0
    for tx in all_tx:
        if tx.possible_duplicate:
            excluded_duplicates += 1
            continue
        g = groups[(tx.investor_id, tx.asset_class.strip().casefold())]
        kind = tx.type.strip().casefold()
        amount = Decimal(tx.amount)
        if kind == 'sip':
            g['contributions'] += amount
        elif kind == 'redemption':
            g['withdrawals'] += amount
        g['source_transaction_rows'].append(tx.source_row_id)
        g['source_instrument_names'].add(tx.instrument_name.strip().casefold())
        if tx.date_confidence == 'QUARANTINED_AMBIGUOUS':
            g['unverified_date_count'] += 1
        if tx.unit_price_confidence == 'UNRELIABLE_AMOUNT_AUTHORITATIVE':
            g['unreliable_sip_units_count'] += 1
    paired = []
    unmatched_tx = []
    unmatched_hold = []
    fund_exact = 0
    fund_total = 0
    for (investor_id, asset_class), g in sorted(groups.items()):
        h_ids = sorted(set(g['source_holding_rows']))
        t_ids = sorted(set(g['source_transaction_rows']))
        if h_ids and t_ids:
            status = 'CLASS_MATCH_ONLY'
            paired.append((investor_id, asset_class))
            fund_total += len(g['source_instrument_names'])
            fund_exact += len(g['source_instrument_names'] & g['matched_holding_names'])
        elif t_ids:
            status = 'TRANSACTIONS_WITHOUT_HOLDINGS_CLASS'
            unmatched_tx.append((investor_id, asset_class))
        else:
            status = 'HOLDINGS_WITHOUT_TRANSACTIONS_CLASS'
            unmatched_hold.append((investor_id, asset_class))
        g['status'] = status
    return {
        'status': 'SOURCE_CROSS_SHEET_REVIEW',
        'holding_class_pairs': sum(bool(g['source_holding_rows']) for g in groups.values()),
        'transaction_class_pairs': sum(bool(g['source_transaction_rows']) for g in groups.values()),
        'matched_investor_class_pairs': len(paired),
        'transaction_only_pairs': len(unmatched_tx),
        'holding_only_pairs': len(unmatched_hold),
        'matched_fund_names_within_paired_classes': fund_exact,
        'unique_transaction_fund_names_within_paired_classes': fund_total,
        'excluded_duplicate_copies': excluded_duplicates,
        'quarantined_date_rows': sum(g['unverified_date_count'] for g in groups.values()),
        'unreliable_sip_unit_price_rows': sum(g['unreliable_sip_units_count'] for g in groups.values()),
        'transaction_only_examples': [
            {'investor_id': investor, 'asset_class': asset} for investor, asset in unmatched_tx[:12]
        ],
        'note': 'Investor+asset-class matching is descriptive, not proof that fund units or balances reconcile. Duplicate candidate copies are excluded from sums, but raw source rows remain retained. Ambiguous dates cannot support a verified return.',
    }
