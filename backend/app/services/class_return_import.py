"""Atomic, provenance-preserving optional return series import.

Supplied class returns are third-party, not validated, and are never seeded
or derived from client portfolio performance. Caller must be authorized.
"""
from __future__ import annotations
import csv
from datetime import date,datetime,timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
from io import StringIO
from sqlalchemy import select

from app.models import AssetClassReturnObservation, AuditEvent

HEADERS={'month','asset_class','return_pct','source_reference'}

class ClassReturnImportError(ValueError):
    pass

def parse_class_returns(content: bytes):
    if not content or len(content)>150_000:
        raise ClassReturnImportError('CSV must be between 1 byte and 150 KB')
    try:
        raw=content.decode('utf-8-sig')
        reader=csv.DictReader(StringIO(raw))
        if not reader.fieldnames or set(reader.fieldnames)!=HEADERS:
            raise ClassReturnImportError('CSV headers must be month,asset_class,return_pct,source_reference')
        records=[]; keys=set()
        for line,item in enumerate(reader,start=2):
            if line>1502:raise ClassReturnImportError('CSV exceeds 1500 return observations')
            try:
                month=item['month'].strip()
                if len(month)==7:month+='-01'
                day=date.fromisoformat(month)
                if day.day!=1:raise ValueError('Month must use first calendar day')
                klass=item['asset_class'].strip()
                source=item['source_reference'].strip()
                raw_pct=item['return_pct'].strip()
                pct=Decimal(raw_pct)
                if (not pct.is_finite() or pct < Decimal('-100') or pct > Decimal('1000')
                        or not klass or len(klass)>100 or not source or len(source)>300):
                    raise ValueError('Invalid class name, source reference, or return bounds')
            except (KeyError, AttributeError,ValueError,InvalidOperation, TypeError) as exc:
                raise ClassReturnImportError(f'Invalid data at CSV row {line}: {exc}') from exc
            key=(klass.casefold(),day)
            if key in keys:raise ClassReturnImportError(f'Duplicate asset-class/month in CSV row {line}')
            keys.add(key)
            records.append((klass,day,pct,source,line))
        if not records:raise ClassReturnImportError('CSV contains no observations')
        return records
    except UnicodeError as exc:
        raise ClassReturnImportError('CSV must be UTF-8') from exc

def import_class_returns(db,user,filename:str,content:bytes):
    rows=parse_class_returns(content)
    # Refuse conflicting data rather than silently rewriting source history.
    existing=db.scalars(select(AssetClassReturnObservation).where(
        AssetClassReturnObservation.organization_id==user.organization_id)).all()
    already={(x.asset_class.casefold(),x.month_date) for x in existing}
    clash=next(((klass,month) for klass,month,*_ in rows if (klass.casefold(),month) in already),None)
    if clash:
        raise ClassReturnImportError(f'Already imported return for {clash[0]} in {clash[1]}. Source evidence is immutable; use a separate organization or obtain a new validated import policy.')
    digest=sha256(content).hexdigest()
    for klass,day,pct,source,line in rows:
        db.add(AssetClassReturnObservation(organization_id=user.organization_id,
             asset_class=klass,month_date=day,reported_return_pct=pct,source_reference=source,
             source_filename=filename[:200],file_sha256=digest,source_row_number=line,
             imported_by=user.id,created_at=datetime.now(timezone.utc)))
    db.add(AuditEvent(organization_id=user.organization_id,actor_id=user.id,
        action='ASSET_CLASS_SOURCE_RETURNS_IMPORTED',entity_type='AssetClassReturnObservation',
        entity_id='BATCH',detail=f'{len(rows)} unverified sourced class-return rows imported; sha256={digest}'))
    db.commit()
    return {'imported':len(rows),'source_sha256':digest,'status':'IMPORTED_UNVERIFIED',
            'warning':'Third-party asset returns are not certified; portfolio and benchmark suitability are not independently verified.'}
