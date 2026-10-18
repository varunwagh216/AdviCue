"""Explicit local administrative assignment of a workbook advisor code to a login account.

Run BEFORE importing to map imported investors to your existing Phase 1 advisor.
"""
import argparse
from sqlalchemy import select
from app.core.database import SessionLocal
from app.models import User


def main():
    parser=argparse.ArgumentParser(description='Bind a local advisor login to external ADVxx code before import')
    parser.add_argument('--email',required=True)
    parser.add_argument('--code',required=True)
    args=parser.parse_args()
    code=args.code.strip().upper()
    with SessionLocal() as db:
        user=db.scalar(select(User).where(User.email==args.email.strip().lower()))
        if user is None or user.role!='ADVISOR':
            parser.error('A real ADVISOR account with that email must already exist')
        already=db.scalar(select(User).where(User.organization_id==user.organization_id,
                                            User.external_advisor_code==code,User.id!=user.id))
        if already:
            parser.error('Code already linked to another advisor. No changes made.')
        if user.external_advisor_code and user.external_advisor_code!=code:
            parser.error('Advisor already linked to a different code. No changes made.')
        user.external_advisor_code=code
        db.commit()
        print(f'Linked {user.email} to {code}. Import this workbook using a SUPERVISOR account.')

if __name__=='__main__':
    main()
