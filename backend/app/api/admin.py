"""Organization-level administration. Never used for client advice authoring."""
from datetime import datetime, timezone
import json
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.core.security import current_user, csrf_protected, require_same_origin
from app.models import Organization, User, Investor, ImportBatch, PatternRun, AuditEvent

router=APIRouter(tags=['Admin and oversight'])

def _admin(user:User)->None:
    if user.role!='SUPERVISOR':
        raise HTTPException(status_code=403,detail='Admin access required')

@router.get('/admin/overview')
def overview(user:User=Depends(current_user),db:Session=Depends(get_db)):
    _admin(user)
    org=db.get(Organization,user.organization_id)
    if org is None:raise HTTPException(status_code=404,detail='Organization unavailable')
    def count(cls):
        return db.scalar(select(func.count()).select_from(cls).where(cls.organization_id==user.organization_id)) or 0
    return {'organization_name':org.name,'approval_required':org.approval_required,
      'database_engine':db.get_bind().dialect.name,
      'investor_count':count(Investor),'advisor_count':db.scalar(select(func.count()).select_from(User).where(
         User.organization_id==user.organization_id,User.role=='ADVISOR',User.is_active.is_(True))) or 0,
      'import_count':count(ImportBatch),'pattern_runs':count(PatternRun),'audit_count':count(AuditEvent),
      'note':'Organization-level oversight. Advisor recommendations remain the responsibility of authorized advisors.'}

class PolicyUpdate(BaseModel):
    approval_required:bool

@router.post('/admin/policy')
def update_policy(payload:PolicyUpdate,request:Request,user:User=Depends(csrf_protected),db:Session=Depends(get_db)):
    require_same_origin(request);_admin(user)
    org=db.get(Organization,user.organization_id)
    if not org:raise HTTPException(status_code=404,detail='Organization unavailable')
    previous=bool(org.approval_required)
    org.approval_required=payload.approval_required
    db.add(AuditEvent(organization_id=user.organization_id,actor_id=user.id,
      action='APPROVAL_POLICY_UPDATED',entity_type='Organization',entity_id=org.id,
      detail=json.dumps({'before':previous,'after':payload.approval_required},sort_keys=True)))
    db.commit()
    return {'approval_required':org.approval_required,'note':'Existing approved records are unchanged.'}

@router.get('/workflow-policy')
def workflow_policy(user:User=Depends(current_user),db:Session=Depends(get_db)):
    org=db.get(Organization,user.organization_id)
    if org is None:raise HTTPException(status_code=404,detail='Organization unavailable')
    return {'approval_required':bool(org.approval_required)}
