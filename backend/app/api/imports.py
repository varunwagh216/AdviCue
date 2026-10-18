from fastapi import APIRouter, Depends, File, HTTPException, Request, UploadFile
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import csrf_protected, current_user, require_same_origin
from app.core.access import may_import
from app.models import DataQualityIssue, ImportBatch, User, Holding, InvestmentTransaction, AssetClassReturnObservation
from app.services.importer import MAX_BYTES, batch_public, commit_workbook, stage_workbook

router=APIRouter(prefix='/imports',tags=['Data Import & Trust'])


def supervisor(user:User):
    if not may_import(user):
        raise HTTPException(status_code=403,detail='Workbook management requires workspace-operator authorization')
    return user


def batch_scope(db:Session,user:User,batch_id:str)->ImportBatch:
    batch=db.scalar(select(ImportBatch).where(ImportBatch.id==batch_id,ImportBatch.organization_id==user.organization_id))
    if not batch:
        raise HTTPException(status_code=404,detail='Import batch not found')
    return batch


@router.post('',status_code=201)
async def upload_workbook(request:Request,file:UploadFile=File(...),
                          user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    supervisor(user)
    content=await file.read(MAX_BYTES+1)
    if len(content)>MAX_BYTES:
        raise HTTPException(status_code=413,detail='Maximum upload size is 10 MB')
    batch=stage_workbook(db,user,file.filename or 'unnamed.xlsx',content)
    return batch_public(batch)


@router.get('')
def list_imports(user:User=Depends(current_user),db:Session=Depends(get_db)):
    supervisor(user)
    batches=db.scalars(select(ImportBatch).where(ImportBatch.organization_id==user.organization_id)
                      .order_by(ImportBatch.created_at.desc()).limit(30)).all()
    return {'items':[batch_public(b) for b in batches]}


@router.get('/asset-returns/summary')
def asset_returns_summary(user:User=Depends(current_user),db:Session=Depends(get_db)):
    supervisor(user)
    rows=db.scalars(select(AssetClassReturnObservation).where(
        AssetClassReturnObservation.organization_id==user.organization_id)).all()
    return {'observations':len(rows),'asset_classes':sorted({r.asset_class for r in rows}),
            'months':len({r.month_date for r in rows}),
            'status':'IMPORTED_UNVERIFIED' if rows else 'NO_RETURN_SOURCE',
            'note':'Optional third-party returns are descriptive proxies, not verified attribution or a suitable approved benchmark.'}

@router.post('/asset-returns/upload',status_code=201)
async def upload_asset_return_csv(request:Request,file:UploadFile=File(...),
      user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    supervisor(user)
    from app.services.class_return_import import import_class_returns,ClassReturnImportError
    if not (file.filename or '').lower().endswith('.csv'):
        raise HTTPException(status_code=422,detail='Supply a UTF-8 .csv source file')
    content=await file.read(150_001)
    try:return import_class_returns(db,user,file.filename or 'asset-class-returns.csv',content)
    except ClassReturnImportError as exc:raise HTTPException(status_code=422,detail=str(exc)) from exc


@router.get('/{batch_id}')
def get_import(batch_id:str,user:User=Depends(current_user),db:Session=Depends(get_db)):
    supervisor(user)
    return batch_public(batch_scope(db,user,batch_id))


@router.get('/{batch_id}/issues')
def get_import_issues(batch_id:str,limit:int=100,offset:int=0,user:User=Depends(current_user),db:Session=Depends(get_db)):
    supervisor(user)
    batch_scope(db,user,batch_id)
    limit=min(max(limit,1),250)
    offset=max(offset,0)
    base=select(DataQualityIssue).where(DataQualityIssue.batch_id==batch_id)
    issues=db.scalars(base.order_by(DataQualityIssue.sheet_name,DataQualityIssue.row_number,DataQualityIssue.code)
                      .offset(offset).limit(limit)).all()
    total=db.scalar(select(func.count()).select_from(DataQualityIssue).where(DataQualityIssue.batch_id==batch_id)) or 0
    return {'total':total,'items':[{'id':i.id,'sheet_name':i.sheet_name,'row_number':i.row_number,'field_name':i.field_name,
                                   'severity':i.severity,'code':i.code,'message':i.message} for i in issues]}


@router.get('/reconciliation/summary')
def get_reconciliation(user: User = Depends(current_user), db: Session = Depends(get_db)):
    """Source reconciliation visible only to authorized workspace operator."""
    supervisor(user)
    from app.services.reconciliation import reconcile_transactions_holdings
    holdings = db.scalars(select(Holding).where(Holding.organization_id == user.organization_id)).all()
    transactions = db.scalars(select(InvestmentTransaction).where(
        InvestmentTransaction.organization_id == user.organization_id)).all()
    return reconcile_transactions_holdings(holdings, transactions)


@router.post('/{batch_id}/commit')
def commit_import(batch_id:str,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request)
    supervisor(user)
    result=commit_workbook(db,user,batch_scope(db,user,batch_id))
    from app.services.monitoring import refresh_clients
    result['monitoring']=refresh_clients(db,user)
    return result


