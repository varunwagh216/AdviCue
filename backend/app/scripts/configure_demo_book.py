"""Expand only the bundled fictional advisor book to 20 clients; preserve raw source ownership."""
from collections import defaultdict, deque
from hashlib import sha256
from pathlib import Path
from sqlalchemy import select


def configure_demo_book(db):
    from app.models import User, Investor, Organization, ImportBatch, AttentionCase, AuditEvent
    advisor=db.scalar(select(User).where(User.email=='advisor@advicue.demo',User.role=='ADVISOR'))
    if not advisor:return {'changed':False,'reason':'Demo advisor is not present.'}
    org=db.get(Organization,advisor.organization_id)
    clients=db.scalars(select(Investor).where(Investor.organization_id==advisor.organization_id).order_by(Investor.id)).all()
    own={i.id for i in clients if i.advisor_id==advisor.id}
    if len(own)==20:return {'changed':False,'assigned_count':20,'reason':'Demo book already contains 20 clients.'}
    workbook=Path(__file__).resolve().parents[3]/'sample_data'/'Transaction History Investor.xlsx'
    expected={f'INV{i:04d}' for i in range(1,49)}
    if not org or org.name!='AdviCue Demo Organization' or {i.id for i in clients}!=expected or not workbook.exists():
        raise RuntimeError('Only the original 48-investor fictional sample organization can be expanded.')
    source_hash=sha256(workbook.read_bytes()).hexdigest()
    batch=db.scalar(select(ImportBatch).where(ImportBatch.organization_id==advisor.organization_id,ImportBatch.file_sha256==source_hash,ImportBatch.status=='COMMITTED'))
    if not batch:raise RuntimeError('Bundled sample import provenance was not found. No ownership changes made.')
    if len(own)>20:raise RuntimeError('Existing book exceeds 20; no clients were removed.')
    selected=own|{f'INV{i:04d}' for i in range(9,17)}
    if len(selected)>20:raise RuntimeError('Existing assignments cannot fit the sample selection; no clients removed.')
    pools=defaultdict(deque)
    for inv in clients:
        if inv.id not in selected:pools[inv.risk_profile or 'Unspecified'].append(inv.id)
    while len(selected)<20:
        for profile in sorted(pools):
            if pools[profile] and len(selected)<20:selected.add(pools[profile].popleft())
    changed=[]
    for inv in clients:
        if inv.id in selected and inv.advisor_id!=advisor.id:
            changed.append({'investor_id':inv.id,'previous_demo_advisor_id':inv.advisor_id,'source_advisor_code':inv.source_advisor_code})
            inv.advisor_id=advisor.id
    for case in db.scalars(select(AttentionCase).where(AttentionCase.organization_id==advisor.organization_id,AttentionCase.investor_id.in_(selected))).all():
        case.advisor_id=advisor.id
    import json
    db.add(AuditEvent(organization_id=advisor.organization_id,actor_id=advisor.id,action='DEMO_BOOK_EXPANDED',entity_type='Investor',entity_id='DEMO_BOOK',detail=json.dumps({'fictional_demo_only':True,'assigned_count':20,'assignments':changed,'source_advisor_codes_preserved':True})))
    db.commit()
    return {'changed':True,'assigned_count':20,'added_count':len(changed),'investor_ids':sorted(selected),'source_advisor_codes_preserved':True}


def main():
    from app.core.config import settings
    if settings.app_env.lower() not in ('demo','development') or not settings.database_url.startswith('sqlite:///'):
        raise SystemExit('Demo expansion is limited to local SQLite demo/development mode.')
    from app.core.database import SessionLocal
    import json
    with SessionLocal() as db:print(json.dumps(configure_demo_book(db),indent=2))

if __name__=='__main__':main()
