"""Idempotent metadata-only trust audit for the bundled imported workbook.

Never deletes, reorders, or alters raw source evidence or investor balances.
Run after Alembic migration: python -m app.scripts.refresh_data_trust
"""
from __future__ import annotations
from collections import Counter
from decimal import Decimal
from sqlalchemy import select,func
from app.core.database import SessionLocal
from app.models import DataQualityIssue, SourceRow, InvestmentTransaction, Holding, ImportBatch, User
from app.services.trust import sip_recurrence_days,date_classification,transaction_unit_quality


def refresh(db):
    transactions=db.scalars(select(InvestmentTransaction)).all()
    src_ids=[t.source_row_id for t in transactions]
    source_rows=db.scalars(select(SourceRow).where(SourceRow.id.in_(src_ids))).all()
    source_map={r.id:r for r in source_rows}
    days=sip_recurrence_days(source_rows)
    known={(i.source_row_id,i.code) for i in db.scalars(select(DataQualityIssue).where(
        DataQualityIssue.source_row_id.in_(src_ids))).all()}
    counts=Counter()
    for tx in transactions:
        source=source_map.get(tx.source_row_id)
        if not source:continue
        normalized={**source.normalized_data}
        confidence=date_classification(source.raw_data.get('date'),
                           investor_id=tx.investor_id,expected_days=days.get(tx.investor_id))
        tx.date_confidence=confidence
        kind=(tx.type or '').strip().lower()
        tx.external_flow_status=('CONTRIBUTION_UNVERIFIED' if kind=='sip' else
                                 'WITHDRAWAL_UNVERIFIED' if kind=='redemption' else 'UNKNOWN')
        tx.unit_price_confidence=transaction_unit_quality(normalized)
        normalized['date_date_quality']=confidence
        normalized['_unit_price_quality']=tx.unit_price_confidence
        source.normalized_data=normalized
        for code,field,message in ([
            ('AMBIGUOUS_SOURCE_DATE','date','Transaction date is ambiguous; inferred only from recorded SIP recurrence or quarantined for timing-sensitive calculations.')
            ] if confidence in ('INFERRED_DAY_FIRST','QUARANTINED_AMBIGUOUS') else []) + ([
            ('UNRELIABLE_SIP_UNITS','units','SIP units and price disagree with amount; amount is authoritative for cash-flow summaries.')
            ] if tx.unit_price_confidence=='UNRELIABLE_AMOUNT_AUTHORITATIVE' else []):
            if (source.id,code) not in known:
                db.add(DataQualityIssue(batch_id=source.batch_id,source_row_id=source.id,
                    sheet_name=source.sheet_name,row_number=source.row_number,field_name=field,
                    severity='WARNING',code=code,message=message))
                known.add((source.id,code));counts[code]+=1
        counts[confidence]+=1
    holdings=db.scalars(select(Holding)).all()
    hold_sources={r.id:r for r in db.scalars(select(SourceRow).where(
            SourceRow.id.in_([h.source_row_id for h in holdings]))).all()}
    holding_known={(i.source_row_id,i.code) for i in db.scalars(select(DataQualityIssue).where(
        DataQualityIssue.source_row_id.in_([h.source_row_id for h in holdings]))).all()}
    for holding in holdings:
        source=hold_sources.get(holding.source_row_id)
        if not source:continue
        quality=date_classification(source.raw_data.get('purchase_date'))
        holding.purchase_date_confidence=quality
        if quality=='QUARANTINED_AMBIGUOUS' and (source.id,'AMBIGUOUS_SOURCE_DATE') not in holding_known:
            db.add(DataQualityIssue(batch_id=source.batch_id,source_row_id=source.id,
                 sheet_name=source.sheet_name,row_number=source.row_number,
                 field_name='purchase_date',severity='WARNING',code='AMBIGUOUS_SOURCE_DATE',
                 message='Purchase date could be day-first or month-first. Quarantined from dated purchase calculations pending confirmation.'))
            counts['AMBIGUOUS_HOLDING_PURCHASE_DATE']+=1
        counts[quality+'_HOLDING']+=1
    for batch_id in {r.batch_id for r in source_rows}|{r.batch_id for r in hold_sources.values()}:
        batch=db.get(ImportBatch,batch_id)
        if batch:batch.warning_count=db.scalar(select(func.count()).select_from(DataQualityIssue).where(
            DataQualityIssue.batch_id==batch_id,DataQualityIssue.severity=='WARNING')) or 0
    # Only create verification cases with a legitimate audit actor in the same org.
    from app.services.attention import sync_source_verification_cases
    organizations = {tx.organization_id for tx in transactions}
    for org_id in organizations:
        actor = db.scalar(select(User).where(User.organization_id==org_id,
            User.email=='advisor@advicue.demo',User.is_active.is_(True)))
        if actor:
            outcome = sync_source_verification_cases(db, org_id, actor.id)
            counts['VERIFY_CASES_CREATED'] += outcome['created']
    db.commit()
    return dict(counts)

if __name__=='__main__':
    with SessionLocal() as db:print('Source trust metadata updated (original evidence preserved):',refresh(db))
