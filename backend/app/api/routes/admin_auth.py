from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session

from app.api.deps import get_current_admin_user, get_db, require_admin_or_super_admin
from app.core.config import settings
from app.models.admin_user import AdminUser
from app.services.admin_auth import (
    AdminAuthError,
    authenticate_admin_user,
    create_admin_user,
    issue_admin_access_token,
    issue_password_reset,
    list_admin_users,
    consume_password_reset,
    update_admin_user,
)

router = APIRouter()


class AdminUserView(BaseModel):
    id: UUID
    email: str
    full_name: str
    role: str
    is_active: bool
    last_login_at: str | None = None
    created_at: str | None = None


class AdminLoginRequest(BaseModel):
    email: EmailStr
    password: str = Field(..., min_length=1, max_length=120)


class AdminLoginResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
    expires_in_minutes: int
    user: AdminUserView


class AdminForgotPasswordRequest(BaseModel):
    email: EmailStr


class AdminResetPasswordRequest(BaseModel):
    token: str = Field(..., min_length=8, max_length=500)
    new_password: str = Field(..., min_length=8, max_length=120)


class AdminUserCreateRequest(BaseModel):
    email: EmailStr
    full_name: str = Field(..., min_length=1, max_length=255)
    role: str = Field(..., min_length=1, max_length=50)
    password: str = Field(..., min_length=8, max_length=120)
    is_active: bool = True


class AdminUserUpdateRequest(BaseModel):
    full_name: str | None = Field(default=None, min_length=1, max_length=255)
    role: str | None = Field(default=None, min_length=1, max_length=50)
    is_active: bool | None = None
    new_password: str | None = Field(default=None, min_length=8, max_length=120)


def _user_view(user: AdminUser) -> AdminUserView:
    return AdminUserView(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        role=user.role,
        is_active=bool(user.is_active),
        last_login_at=user.last_login_at.isoformat() if user.last_login_at else None,
        created_at=user.created_at.isoformat() if user.created_at else None,
    )


@router.post("/auth/login", response_model=AdminLoginResponse)
def admin_login(payload: AdminLoginRequest, db: Session = Depends(get_db)) -> AdminLoginResponse:
    user = authenticate_admin_user(db=db, email=payload.email, password=payload.password)
    if user is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid email or password.")

    token = issue_admin_access_token(user=user)
    return AdminLoginResponse(
        access_token=token,
        expires_in_minutes=settings.access_token_expire_minutes,
        user=_user_view(user),
    )


@router.get("/auth/me", response_model=AdminUserView)
def admin_me(current_user: AdminUser = Depends(get_current_admin_user)) -> AdminUserView:
    return _user_view(current_user)


@router.post("/auth/forgot-password")
def admin_forgot_password(
    payload: AdminForgotPasswordRequest,
    request: Request,
    db: Session = Depends(get_db),
) -> dict[str, str]:
    result = issue_password_reset(db=db, email=payload.email, request_base_url=str(request.base_url).rstrip("/"))
    response = {
        "status": "ok",
        "message": "If the email exists, a reset link has been sent.",
        "delivery": result.delivery,
    }
    if result.preview_link:
        response["preview_link"] = result.preview_link
    return response


@router.post("/auth/reset-password")
def admin_reset_password(payload: AdminResetPasswordRequest, db: Session = Depends(get_db)) -> dict[str, str]:
    try:
        consume_password_reset(db=db, token=payload.token, new_password=payload.new_password)
    except AdminAuthError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return {"status": "ok", "message": "Password has been reset. Please sign in with your new password."}


@router.get("/users")
def admin_list_users(
    _manager: AdminUser = Depends(require_admin_or_super_admin),
    db: Session = Depends(get_db),
) -> dict[str, object]:
    users = list_admin_users(db=db)
    return {"items": [_user_view(item).model_dump() for item in users], "count": len(users)}


@router.post("/users", response_model=AdminUserView)
def admin_create_user(
    payload: AdminUserCreateRequest,
    current_user: AdminUser = Depends(require_admin_or_super_admin),
    db: Session = Depends(get_db),
) -> AdminUserView:
    requested_role = str(payload.role or "").strip().lower()
    if requested_role == "accountant":
        requested_role = "monitor"
    if requested_role == "super_admin" and current_user.role != "super_admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only super admin can create another super admin user.",
        )
    try:
        user = create_admin_user(
            db=db,
            email=payload.email,
            full_name=payload.full_name,
            role=requested_role,
            password=payload.password,
            is_active=payload.is_active,
        )
    except AdminAuthError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return _user_view(user)


@router.patch("/users/{user_id}", response_model=AdminUserView)
def admin_update_user(
    user_id: UUID,
    payload: AdminUserUpdateRequest,
    current_user: AdminUser = Depends(require_admin_or_super_admin),
    db: Session = Depends(get_db),
) -> AdminUserView:
    requested_role = payload.role
    if requested_role is not None:
        normalized = str(requested_role).strip().lower()
        if normalized == "accountant":
            normalized = "monitor"
        if normalized == "super_admin" and current_user.role != "super_admin":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only super admin can promote a user to super admin.",
            )
        requested_role = normalized
    try:
        user = update_admin_user(
            db=db,
            user_id=user_id,
            full_name=payload.full_name,
            role=requested_role,
            is_active=payload.is_active,
            new_password=payload.new_password,
        )
    except AdminAuthError as exc:
        detail = str(exc)
        code = status.HTTP_404_NOT_FOUND if "not found" in detail.lower() else status.HTTP_422_UNPROCESSABLE_ENTITY
        raise HTTPException(status_code=code, detail=detail) from exc
    return _user_view(user)
