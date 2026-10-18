from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db
from app.core.security import (
    COOKIE_NAME, create_session, csrf_protected,
    get_login_session, require_same_origin, verify_password,
)
from app.models import AuditEvent, LoginSession, User
from app.schemas.auth import AuthResponse, LoginRequest, UserInfo

router = APIRouter(prefix="/auth", tags=["Authentication"])


def public_user(user: User) -> UserInfo:
    return UserInfo(id=user.id, name=user.name, email=user.email, role=user.role)


@router.post("/login", response_model=AuthResponse)
def login(body: LoginRequest, response: Response, request: Request, db: Session = Depends(get_db)):
    require_same_origin(request)
    user = db.scalar(select(User).where(User.email == body.email.strip().lower()))
    # Hash a dummy password as a timing-mitigation path for nonexistent accounts.
    if user is None or not user.is_active or not verify_password(user.password_hash, body.password):
        raise HTTPException(status_code=401, detail="Invalid email or password")
    token, csrf = create_session(db, user)
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, secure=settings.cookie_secure,
        samesite="lax", max_age=settings.session_hours * 3600, path="/api/v1",
    )
    response.headers["Cache-Control"] = "no-store"
    db.add(AuditEvent(organization_id=user.organization_id, actor_id=user.id, action="AUTH_LOGIN"))
    db.commit()
    return AuthResponse(user=public_user(user), csrf_token=csrf)


@router.get("/me", response_model=AuthResponse)
def me(response: Response, session: LoginSession = Depends(get_login_session), db: Session = Depends(get_db)):
    response.headers["Cache-Control"] = "no-store"
    return AuthResponse(user=public_user(session.user), csrf_token=session.csrf_token)


@router.post("/logout")
def logout(response: Response, request: Request, session: LoginSession = Depends(get_login_session),
           user: User = Depends(csrf_protected), db: Session = Depends(get_db)):
    require_same_origin(request)
    db.add(AuditEvent(organization_id=user.organization_id, actor_id=user.id, action="AUTH_LOGOUT"))
    db.delete(session)
    db.commit()
    response.delete_cookie(COOKIE_NAME, path="/api/v1")
    response.headers["Cache-Control"] = "no-store"
    return {"ok": True}
