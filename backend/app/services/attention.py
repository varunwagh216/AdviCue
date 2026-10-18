"""Persistent cases for the Phase 4 explainable pattern results.

A rescan of the same dated source does not create duplicate cases or reopen a
case that an advisor has already resolved. A newer dated snapshot may produce
a new case; no automatic suitability finding is made.
"""
from datetime import datetime, timezone
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AttentionCase, AuditEvent, PatternMember, DetectedPattern, PerformanceSnapshot, Investor
from app.engines.advanced import reported_comparison, priority_components


def _case_precedence(case: AttentionCase):
    """High-confidence advanced signal wins over legacy same-day signals.

    Preserves pre-existing advice links by recording supersession, not deleting cases.
    """
    advanced = (case.rule_id or '').startswith('PAT_PEER_')
    priority = {'P1': 3, 'P2': 2, 'P3': 1, 'V_VERIFY': 0}.get(case.priority, 0)
    return (case.source_date, advanced, priority, case.created_at or datetime.min.replace(tzinfo=timezone.utc), case.id)


def consolidate_attention_cases(db: Session, organization_id: str, actor_id: str | None = None) -> dict:
    """Idempotently mark non-canonical review cases as historical, preserving every row.

    One current review case per investor; other underlying patterns stay in Pattern Explorer.
    Rescans may update priorities but cannot replace previously resolved records' history.
    """
    from collections import defaultdict
    grouped = defaultdict(list)
    for case in db.scalars(select(AttentionCase).where(AttentionCase.organization_id == organization_id)).all():
        if case.rule_id.startswith(('MANUAL_','MON_')):continue
        grouped[(case.investor_id, case.priority == 'V_VERIFY')].append(case)
    changed = 0
    for investor_id, cases in grouped.items():
        if len(cases) <= 1:
            if cases and cases[0].superseded_by_id is not None:
                cases[0].superseded_by_id = None
                changed += 1
            continue
        # Date, version, and priority take precedence; never choose an old resolved review
        # over a newer actionable case unless no other case exists.
        canonical = max(cases, key=_case_precedence)
        for case in cases:
            desired = None if case.id == canonical.id else canonical.id
            if case.superseded_by_id != desired:
                case.superseded_by_id = desired
                changed += 1
    if changed and actor_id:
        db.add(AuditEvent(organization_id=organization_id, actor_id=actor_id,
            action='ATTENTION_SUPERSESSION_SYNC', entity_type='AttentionCase', entity_id='BOOK',
            detail=f'Updated {changed} case supersession links. Historical records retained.'))
    return {'supersession_links_changed': changed, 'current_review_streams': len(grouped)}


def sync_source_verification_cases(db: Session, organization_id: str, actor_id: str) -> dict:
    """Turn quarantined transaction dates into independent V_VERIFY cases.

    These do not imply benchmark underperformance, suitability or trading advice.
    Deterministic and idempotent; raw imported records stay unmodified.
    """
    from collections import defaultdict
    from sqlalchemy import func
    from app.models import Holding, InvestmentTransaction
    uncertain = db.scalars(select(InvestmentTransaction).where(
        InvestmentTransaction.organization_id == organization_id,
        InvestmentTransaction.date_confidence == 'QUARANTINED_AMBIGUOUS',
        InvestmentTransaction.possible_duplicate.is_(False))).all()
    by_investor = defaultdict(list)
    for tx in uncertain:
        by_investor[tx.investor_id].append(tx)
    created = 0
    for investor_id, rows in by_investor.items():
        inv = db.get(Investor, investor_id)
        if not inv or inv.organization_id != organization_id:
            continue
        latest = db.scalar(select(func.max(Holding.as_of_date)).where(
            Holding.organization_id == organization_id, Holding.investor_id == investor_id))
        source_date = latest or max(tx.date for tx in rows)
        existing = db.scalar(select(AttentionCase).where(
            AttentionCase.organization_id == organization_id,
            AttentionCase.investor_id == investor_id,
            AttentionCase.rule_id == 'TRUST_UNCERTAIN_TRANSACTION_DATES',
            AttentionCase.source_date == source_date))
        evidence = sorted({tx.source_row_id for tx in rows})
        if existing:
            if existing.status != 'RESOLVED':
                existing.evidence_source_row_ids = evidence
            continue
        db.add(AttentionCase(organization_id=organization_id, investor_id=investor_id,
            advisor_id=inv.advisor_id, pattern_id=None, rule_id='TRUST_UNCERTAIN_TRANSACTION_DATES',
            rule_version='1.0',source_date=source_date,priority='V_VERIFY',status='NEEDS_DATA',
            title='Verify ambiguous transaction dates',
            reason=f'{len(evidence)} non-duplicate transaction source rows have ambiguous day-first/month-first dates. Their timing is excluded from behavior calculations and cash-flow performance remains unverified.',
            suggested_action='Confirm dated transaction source documents or obtain corrected provider records before return calculations. Do not interpret this as a loss or investment suitability problem.',
            evidence_source_row_ids=evidence))
        created += 1
    db.flush()
    consolidate_attention_cases(db, organization_id, actor_id)
    if created:
        db.add(AuditEvent(organization_id=organization_id, actor_id=actor_id,
            action='DATA_VERIFY_CASE_SYNC', entity_type='AttentionCase', entity_id='BOOK',
            detail=f'{created} data verification review cases created from quarantined date evidence.'))
    return {'created': created, 'affected_investors': len(by_investor)}


def create_or_update_pattern_cases(db: Session, pattern: DetectedPattern, actor_id: str) -> dict:
    matched=db.scalars(select(PatternMember).where(PatternMember.pattern_id==pattern.id)).all()
    created=updated=0
    for m in matched:
        snaps=db.scalars(select(PerformanceSnapshot).where(PerformanceSnapshot.organization_id==pattern.organization_id,
                       PerformanceSnapshot.investor_id==m.investor_id)).all()
        inv=db.get(Investor,m.investor_id)
        score=priority_components(reported_comparison(snaps),m.recorded_value,
                inv.goal_target_date if inv else None,pattern.snapshot_date)
        case=db.scalar(select(AttentionCase).where(
            AttentionCase.organization_id==pattern.organization_id,
            AttentionCase.investor_id==m.investor_id,
            AttentionCase.rule_id==pattern.rule_id,
            AttentionCase.source_date==pattern.snapshot_date))
        if case:
            case.pattern_id=pattern.id
            if case.status!='RESOLVED':case.priority=score['band']
            case.rule_version=pattern.rule_version
            # Preserve explicit client review decisions and original evidence.
            case.updated_at=datetime.now(timezone.utc)
            updated+=1
            continue
        db.add(AttentionCase(
            organization_id=pattern.organization_id, investor_id=m.investor_id,
            advisor_id=m.advisor_id, pattern_id=pattern.id,
            rule_id=pattern.rule_id, rule_version=pattern.rule_version,
            source_date=pattern.snapshot_date,
            priority=score['band'], status='OPEN',
            title='Allocation pattern requires mandate review',
            reason=f'As of {pattern.snapshot_date.isoformat()}, recorded equity weight is {m.equity_pct}% and fixed-deposit weight is {m.fixed_deposit_pct}%. Pattern rule {pattern.rule_id} v{pattern.rule_version}. Reported-data triage score {score["score"]} ({score["components"]}); not a verified return or suitability conclusion.',
            suggested_action='Confirm the investor\'s approved mandate, investment horizon, and liquidity needs. Validate whether the dated holdings still reflect the client\'s portfolio.',
            evidence_source_row_ids=m.evidence_source_row_ids,
        ))
        created+=1
    consolidate_attention_cases(db, pattern.organization_id, actor_id)
    db.add(AuditEvent(organization_id=pattern.organization_id, actor_id=actor_id,
        action='ATTENTION_CASE_SYNC', entity_type='DetectedPattern', entity_id=pattern.id,
        detail=f'Created {created} new client review cases; refreshed {updated} existing cases.'))
    return {'created':created,'updated':updated}
