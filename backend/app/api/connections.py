"""Reviewed generic CSV intake and user-controlled task/calendar exports."""
import csv,io,json
from datetime import date,datetime,timezone
from decimal import Decimal,InvalidOperation
from hashlib import sha256
from fastapi import APIRouter,Depends,Request,HTTPException,UploadFile,File
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import current_user,csrf_protected,require_same_origin
from app.models import User,Investor,ImportBatch,SourceRow,Holding,AuditEvent,PilotSession
from app.api.workflow import list_tasks
from app.services.monitoring import refresh_clients

router=APIRouter(tags=['Data connections'])
HEADERS=['client_id','holding_id','as_of_date','asset_class','instrument_name','current_value']


def advisor(user):
    if user.role!='ADVISOR':raise HTTPException(status_code=403,detail='Assigned advisor required')


def safe_cell(value):
    value='' if value is None else str(value)
    return "'"+value if value.lstrip().startswith(('=','+','-','@')) or value.startswith(('\t','\r','\n')) else value


@router.get('/connections/holdings-template.csv')
def template(user:User=Depends(current_user)):
    return Response(','.join(HEADERS)+'\nYOUR_CLIENT_ID,provider-holding-id,YYYY-MM-DD,Direct Equity,Instrument name,100000.00\n',media_type='text/csv',headers={'Content-Disposition':'attachment; filename=holdings-template.csv'})


@router.post('/connections/holdings-csv',status_code=201)
async def preview(request:Request,file:UploadFile=File(...),user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request);advisor(user);data=await file.read(2*1024*1024+1);await file.close()
    if not data or len(data)>2*1024*1024:raise HTTPException(status_code=413,detail='Choose a nonempty CSV smaller than 2 MB')
    try:
        reader=csv.DictReader(io.StringIO(data.decode('utf-8-sig')))
        if not reader.fieldnames or set(reader.fieldnames)!=set(HEADERS):raise ValueError('Use the six template columns exactly; UTF-8 CSV with a header is required')
        raw=list(reader)
        if not 1<=len(raw)<=10000:raise ValueError('Use between 1 and 10,000 holdings rows')
        normalized=[];seen=set();days={}
        allowed={i.id:i for i in db.scalars(select(Investor).where(Investor.organization_id==user.organization_id,Investor.advisor_id==user.id)).all()}
        for n,row in enumerate(raw,2):
            if None in row or any(v is None for v in row.values()):raise ValueError(f'Row {n}: incorrect column count')
            values={k:v.strip() for k,v in row.items()}
            if values['client_id'] not in allowed:raise HTTPException(status_code=404,detail='CSV includes a client outside your assigned records')
            day=date.fromisoformat(values['as_of_date'])
            if day>date.today():raise ValueError(f'Row {n}: future holdings dates are not accepted')
            amount=Decimal(values['current_value'])
            if not amount.is_finite() or amount<0 or amount>10**15 or amount!=amount.quantize(Decimal('.01')):raise ValueError(f'Row {n}: use a nonnegative value with at most two decimal places')
            if not values['holding_id'] or len(values['holding_id'])>40 or not 2<=len(values['asset_class'])<=80 or not 2<=len(values['instrument_name'])<=200:raise ValueError(f'Row {n}: a provider holding ID, asset class and instrument name are required')
            key=(values['client_id'],values['holding_id'],day)
            if key in seen:raise ValueError(f'Row {n}: duplicate client/holding/date')
            seen.add(key)
            if values['client_id'] in days and days[values['client_id']]!=day:raise ValueError('Supply one complete valuation date per client per CSV')
            days[values['client_id']]=day;values['current_value']=str(amount);normalized.append(values)
    except (ValueError,UnicodeError,csv.Error,InvalidOperation) as exc:raise HTTPException(status_code=422,detail=str(exc))
    digest=sha256(b'advicue-holdings-csv-v6\0'+data).hexdigest()
    existing=db.scalar(select(ImportBatch).where(ImportBatch.organization_id==user.organization_id,ImportBatch.file_sha256==digest))
    if existing:
        if existing.uploaded_by!=user.id:raise HTTPException(status_code=404,detail='Import not found')
        return {'id':existing.id,'status':existing.status,'rows':len(normalized),'clients':len(days),'duplicate':True}
    batch=ImportBatch(organization_id=user.organization_id,uploaded_by=user.id,filename=(file.filename or 'holdings.csv')[:240],file_sha256=digest,status='CSV_STAGED',total_rows=len(raw),sheet_counts={'holdings_csv':len(raw)})
    db.add(batch);db.flush()
    for n,(source,values) in enumerate(zip(raw,normalized),2):db.add(SourceRow(batch_id=batch.id,sheet_name='holdings_csv',row_number=n,raw_data=source,normalized_data=values))
    db.add(AuditEvent(organization_id=user.organization_id,actor_id=user.id,action='CSV_HOLDINGS_STAGED',entity_type='ImportBatch',entity_id=batch.id,detail=json.dumps({'rows':len(raw),'clients':len(days),'sha256':digest})))
    db.commit();return {'id':batch.id,'status':batch.status,'rows':len(raw),'clients':len(days),'preview':[{'client_name':allowed[x['client_id']].display_name,**x} for x in normalized[:10]],'note':'Preview only. Confirm this is a complete snapshot for each client/date before committing. Historical source rows are retained; conflicting same-date snapshots are refused.'}


class ConfirmCSV(BaseModel):
    complete_snapshot:bool


@router.post('/connections/holdings-csv/{batch_id}/commit')
def commit(batch_id:str,payload:ConfirmCSV,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request);advisor(user)
    batch=db.scalar(select(ImportBatch).where(ImportBatch.id==batch_id,ImportBatch.organization_id==user.organization_id,ImportBatch.uploaded_by==user.id))
    if not batch or not batch.sheet_counts.get('holdings_csv'):raise HTTPException(status_code=404,detail='CSV import not found')
    if batch.status=='COMMITTED':return {'id':batch.id,'status':'COMMITTED','already_committed':True}
    if batch.status!='CSV_STAGED' or not payload.complete_snapshot:raise HTTPException(status_code=422,detail='Review and confirm complete client snapshots before committing')
    rows=db.scalars(select(SourceRow).where(SourceRow.batch_id==batch.id)).all();grouped={}
    for row in rows:
        d=row.normalized_data;inv=db.get(Investor,d['client_id'])
        if not inv or inv.organization_id!=user.organization_id or inv.advisor_id!=user.id:raise HTTPException(status_code=404,detail='Client assignment changed; restage with current assigned records')
        grouped.setdefault((inv.id,d['as_of_date']),[]).append(row)
    skip=set()
    for (iid,day),new in grouped.items():
        old=db.scalars(select(Holding).where(Holding.organization_id==user.organization_id,Holding.investor_id==iid,Holding.as_of_date==date.fromisoformat(day))).all()
        canonical=lambda h:(h.external_holding_id,h.asset_class,h.instrument_name,Decimal(h.current_value))
        incoming={(r.normalized_data['holding_id'],r.normalized_data['asset_class'],r.normalized_data['instrument_name'],Decimal(r.normalized_data['current_value'])) for r in new}
        if old:
            if {canonical(h) for h in old}==incoming:skip.update(r.id for r in new)
            else:raise HTTPException(status_code=409,detail='A different snapshot already exists for a client/date. No holdings changed. Resolve source corrections explicitly or import the next complete dated snapshot.')
    for row in rows:
        if row.id in skip:continue
        d=row.normalized_data;db.add(Holding(organization_id=user.organization_id,investor_id=d['client_id'],source_row_id=row.id,external_holding_id=d['holding_id'],as_of_date=date.fromisoformat(d['as_of_date']),asset_class=d['asset_class'],instrument_name=d['instrument_name'],current_value=Decimal(d['current_value'])))
    batch.status='COMMITTED';batch.committed_at=datetime.now(timezone.utc)
    db.add(AuditEvent(organization_id=user.organization_id,actor_id=user.id,action='CSV_HOLDINGS_COMMITTED',entity_type='ImportBatch',entity_id=batch.id,detail=json.dumps({'rows_added':len(rows)-len(skip),'duplicate_rows_skipped':len(skip),'complete_snapshot_attested':True,'sha256':batch.file_sha256})))
    db.commit();monitoring=refresh_clients(db,user)
    return {'id':batch.id,'status':'COMMITTED','rows_added':len(rows)-len(skip),'monitoring':monitoring}


@router.get('/connections/follow-ups.csv')
def task_csv(user:User=Depends(current_user),db:Session=Depends(get_db)):
    advisor(user);rows=list_tasks(user,db)['items'];stream=io.StringIO(newline='');writer=csv.writer(stream)
    writer.writerow(['task_id','client_name','title','due_date','status','completion_note'])
    for t in rows:writer.writerow([safe_cell(t[k]) for k in ('id','investor_name','title','due_date','status','completion_note')])
    return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=advicue-follow-ups.csv'})


@router.get('/connections/follow-ups.ics')
def calendar(user:User=Depends(current_user),db:Session=Depends(get_db)):
    advisor(user);rows=list_tasks(user,db)['items'];lines=['BEGIN:VCALENDAR','VERSION:2.0','PRODID:-//AdviCue//Advisor Tasks//EN']
    def escaped(value):return str(value or '').replace('\\','\\\\').replace('\r','').replace('\n','\\n').replace(';','\\;').replace(',','\\,')
    for t in rows:
        lines+=['BEGIN:VTODO','UID:'+t['id']+'@advicue.local','DTSTAMP:'+datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ'),'DUE;VALUE=DATE:'+t['due_date'].replace('-',''),'SUMMARY:'+escaped(t['investor_name']+' — '+t['title']),'DESCRIPTION:'+escaped(t['completion_note'] or 'Review the linked task in AdviCue.'),'STATUS:'+('COMPLETED' if t['status']=='DONE' else 'CANCELLED' if t['status']=='CANNOT_VERIFY' else 'IN-PROCESS' if t['status']=='IN_PROGRESS' else 'NEEDS-ACTION'),'END:VTODO']
    lines+=['END:VCALENDAR'];folded=[]
    for line in lines:
        part=''
        for char in line:
            if len((part+char).encode('utf-8'))>73:folded.append(part);part=' '+char
            else:part+=char
        folded.append(part)
    return Response('\r\n'.join(folded)+'\r\n',media_type='text/calendar',headers={'Content-Disposition':'attachment; filename=advicue-follow-ups.ics'})


@router.get('/pilot/observations.csv')
def pilot_export(user:User=Depends(current_user),db:Session=Depends(get_db)):
    advisor(user)
    rows=db.scalars(select(PilotSession).join(Investor,Investor.id==PilotSession.investor_id).where(PilotSession.organization_id==user.organization_id,PilotSession.advisor_id==user.id,Investor.organization_id==user.organization_id,Investor.advisor_id==user.id).order_by(PilotSession.started_at)).all()
    stream=io.StringIO(newline='');writer=csv.writer(stream)
    fields=['sampling_method','started_at','finished_at','elapsed_seconds','outcome','already_known','discovery_note','missed_issue','voluntary_return','baseline_seconds']
    writer.writerow(['session_id','client_name','case_id']+fields)
    for row in rows:writer.writerow([safe_cell(row.id),safe_cell(db.get(Investor,row.investor_id).display_name),safe_cell(row.case_id)]+[safe_cell(getattr(row,key)) for key in fields])
    return Response(stream.getvalue(),media_type='text/csv',headers={'Content-Disposition':'attachment; filename=advicue-pilot-observations.csv'})
