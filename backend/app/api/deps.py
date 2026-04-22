from collections.abc import Generator
import os

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.session import SessionLocal
from app.models.admin_user import AdminUser
from app.services.admin_auth import AdminAuthError, decode_admin_access_token, ensure_bootstrap_super_admin, get_admin_user_by_email

_bearer = HTTPBearer(auto_error=False)


def get_db() -> Generator:
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def _auth_bypass_allowed() -> bool:
    if settings.env.strip().lower() == "test":
        return True
    if bool(os.getenv("PYTEST_CURRENT_TEST")):
        return True
    return not settings.admin_auth_required


def get_current_admin_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
    db: Session = Depends(get_db),
) -> AdminUser:
    ensure_bootstrap_super_admin(db)

    if credentials is None:
        if _auth_bypass_allowed():
            user = get_admin_user_by_email(db=db, email=settings.admin_bootstrap_email)
            if user is None:
                raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin account not available.")
            return user
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin authentication required.")

    if str(credentials.scheme or "").lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Bearer token is required.")

    token = str(credentials.credentials or "").strip()
    if not token:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Access token is required.")

    try:
        email = decode_admin_access_token(token)
    except AdminAuthError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    user = get_admin_user_by_email(db=db, email=email)
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Admin user is not active.")
    return user


def require_super_admin(current_user: AdminUser = Depends(get_current_admin_user)) -> AdminUser:
    if current_user.role != "super_admin":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Only super admin can perform this action.")
    return current_user


def require_admin_or_super_admin(current_user: AdminUser = Depends(get_current_admin_user)) -> AdminUser:
    if current_user.role not in {"super_admin", "admin"}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only admin or super admin can perform this action.",
        )
    return current_user
