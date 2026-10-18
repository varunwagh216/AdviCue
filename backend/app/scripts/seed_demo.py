"""Create a named *fictional* demo user. Requires an explicit password."""
import argparse
import sys
from sqlalchemy import select

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import Organization, User


def main():
    parser = argparse.ArgumentParser(description="Create local demo user after migrations")
    parser.add_argument("--email", default="advisor@advicue.local")
    parser.add_argument("--name", default="Demo Advisor")
    parser.add_argument("--password", required=True, help="Local-only demo password; do not reuse a real password")
    parser.add_argument("--role", choices=["ADVISOR", "SUPERVISOR"], default="ADVISOR")
    args = parser.parse_args()
    if len(args.password) < 12:
        parser.error("Please choose a demo password of at least 12 characters")
    with SessionLocal() as db:
        if db.scalar(select(User).where(User.email == args.email.lower())):
            print("User already exists; no credentials were changed.")
            return
        org = db.scalar(select(Organization).where(Organization.name == "AdviCue Demo Organization"))
        if not org:
            org = Organization(name="AdviCue Demo Organization")
            db.add(org)
            db.flush()
        user = User(
            organization_id=org.id, name=args.name, email=args.email.lower(),
            role=args.role, password_hash=hash_password(args.password),
        )
        db.add(user)
        db.commit()
        print(f"Demo {args.role.lower()} created: {user.email}")
        print("Use the supervisor role for workbook import; advisors only see their assigned clients.")


if __name__ == "__main__":
    main()
