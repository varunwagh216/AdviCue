"""Activate a disabled workbook-created demo advisor without changing assigned investors.

This is an explicitly local administrator CLI; it is not an API route.

Example (from backend/):
python -m app.scripts.activate_imported_advisor --code ADV06 \
    --email advisor6@advicue.local --name "Demo Advisor ADV06" --password "UseYourOwnStrongPassword!"
"""
from __future__ import annotations
import argparse
from sqlalchemy import select
from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import AuditEvent, Organization, User


def main():
    parser=argparse.ArgumentParser(description='Activate a disabled, import-generated demo advisor')
    parser.add_argument('--code',required=True,help='Workbook advisor code e.g. ADV06')
    parser.add_argument('--organization-id',help='Explicit organization ID (for non-default development fixtures)')
    parser.add_argument('--email',required=True,help='Unique demo login email')
    parser.add_argument('--name',required=True,help='Display name')
    parser.add_argument('--password',required=True,help='New local-only password, 12+ characters')
    args=parser.parse_args()
    code=args.code.strip().upper()
    email=args.email.strip().lower()
    name=args.name.strip()
    if len(args.password)<12:parser.error('Password must be at least 12 characters')
    if not email or '@' not in email or len(email)>255:parser.error('Enter a valid demo email address')
    if not name or len(name)>120:parser.error('Enter a display name of 1–120 characters')
    with SessionLocal() as db:
        org=(db.get(Organization,args.organization_id) if args.organization_id else
             db.scalar(select(Organization).where(Organization.name=='AdviCue Demo Organization')))
        if org is None:parser.error('Demo organization does not exist. Import and commit the workbook first.')
        user=db.scalar(select(User).where(User.organization_id==org.id,User.external_advisor_code==code))
        if user is None:parser.error(f'No imported advisor exists for {code}; import the workbook first.')
        if user.role!='ADVISOR' or user.is_active or user.password_hash!='DISABLED_NO_LOGIN' or not user.email.endswith('@advicue.invalid'):
            parser.error('This code is not an inactive workbook-generated placeholder. Existing accounts cannot be overwritten.')
        exists=db.scalar(select(User).where(User.email==email))
        if exists:parser.error('Login email already exists; choose a different email.')
        user.email=email
        user.name=name
        user.password_hash=hash_password(args.password)
        user.is_active=True
        db.add(AuditEvent(organization_id=org.id,actor_id=user.id,action='DEMO_ADVISOR_ACTIVATED',entity_type='User',entity_id=user.id,detail=f'Activated local demo login for code {code}'))
        db.commit()
        print(f'Activated {email} for workbook advisor code {code}. Existing investor assignments are unchanged.')

if __name__=='__main__':main()
