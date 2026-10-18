import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone

from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Cookie, Depends, Header, HTTPException, Request, status
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.models import LoginSession, User

COOKIE_NAME = "advicue_session"
ph = PasswordHasher()


def hash_password(password: str) -> str:
    return ph.hash(password)


def verify_password(stored_hash: str, password: str) -> bool:
    try:
        return ph.verify(stored_hash, password)
    except (VerifyMismatchError, VerificationError):
        return False


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def create_session(db: Session, user: User) -> tuple[str, str]:
    token = secrets.token_urlsafe(40)
    csrf = secrets.token_urlsafe(32)
    db.add(LoginSession(
        token_hash=fingerprint(token),
        user_id=user.id,
        csrf_token=csrf,
        expires_at=datetime.now(timezone.utc) + timedelta(hours=settings.session_hours),
    ))
    db.commit()
    return token, csrf


def get_login_session(
    session_cookie: str | None = Cookie(default=None, alias=COOKIE_NAME),
    db: Session = Depends(get_db),
) -> LoginSession:
    if not session_cookie:
        raise HTTPException(status_code=401, detail="Not authenticated")
    record = db.get(LoginSession, fingerprint(session_cookie))
    if not record:
        raise HTTPException(status_code=401, detail="Session not found")
    expiry = record.expires_at
    if expiry.tzinfo is None:
        expiry = expiry.replace(tzinfo=timezone.utc)
    if expiry <= datetime.now(timezone.utc):
        db.delete(record)
        db.commit()
        raise HTTPException(status_code=401, detail="Session expired")
    if not record.user.is_active:
        raise HTTPException(status_code=403, detail="Account disabled")
    return record


def current_user(session: LoginSession = Depends(get_login_session)) -> User:
    return session.user


def csrf_protected(
    session: LoginSession = Depends(get_login_session),
    csrf_token: str | None = Header(default=None, alias="X-CSRF-Token"),
) -> User:
    if not csrf_token or not hmac.compare_digest(csrf_token, session.csrf_token):
        raise HTTPException(status_code=403, detail="Invalid CSRF token")
    return session.user


def require_same_origin(request: Request) -> None:
    origin = request.headers.get("origin")
    allowed = {settings.frontend_origin.rstrip("/")}
    if settings.app_env.lower() in {"development", "demo", "local"}:
        allowed.update({"http://localhost:5173", "http://127.0.0.1:5173"})
    if origin and origin.rstrip("/") not in allowed:
        raise HTTPException(status_code=403, detail="Untrusted request origin")
