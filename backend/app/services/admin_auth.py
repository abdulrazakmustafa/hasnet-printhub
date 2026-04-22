from __future__ import annotations

import hashlib
import json
import secrets
import smtplib
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from typing import Any
from uuid import UUID

from jose import JWTError, jwt
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.security import create_access_token, get_password_hash, verify_password
from app.models.admin_user import AdminUser

ALLOWED_ADMIN_ROLES = {"super_admin", "admin", "technician", "monitor"}
_PASSWORD_RESET_STORE_PATH = Path(__file__).resolve().parents[2] / "assets" / "admin-password-reset-tokens.json"


class AdminAuthError(RuntimeError):
    pass


@dataclass(slots=True)
class PasswordResetIssueResult:
    delivery: str
    preview_link: str | None = None


def _now_utc() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_email(email: str) -> str:
    return str(email or "").strip().lower()


def _normalize_role(role: str) -> str:
    normalized = str(role or "").strip().lower()
    if normalized == "accountant":
        normalized = "monitor"
    if normalized not in ALLOWED_ADMIN_ROLES:
        raise AdminAuthError("role must be one of: super_admin, admin, technician, monitor")
    return normalized


def _serialize_dt(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _parse_dt(value: str | None) -> datetime | None:
    text = str(value or "").strip()
    if not text:
        return None
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _read_reset_store() -> dict[str, Any]:
    if not _PASSWORD_RESET_STORE_PATH.exists():
        return {"items": []}
    try:
        payload = json.loads(_PASSWORD_RESET_STORE_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"items": []}
    if not isinstance(payload, dict):
        return {"items": []}
    items = payload.get("items")
    if not isinstance(items, list):
        return {"items": []}
    return {"items": items}


def _write_reset_store(payload: dict[str, Any]) -> None:
    _PASSWORD_RESET_STORE_PATH.parent.mkdir(parents=True, exist_ok=True)
    _PASSWORD_RESET_STORE_PATH.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def _hash_reset_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def _send_reset_email(*, recipient: str, full_name: str, reset_link: str) -> bool:
    smtp_host = str(settings.smtp_host or "").strip()
    smtp_from = str(settings.smtp_from or "").strip()
    if not smtp_host or not smtp_from:
        return False

    message = EmailMessage()
    message["From"] = smtp_from
    message["To"] = recipient
    message["Subject"] = "Hasnet PrintHub Admin Password Reset"
    message.set_content(
        (
            f"Habari {full_name},\n\n"
            "A password reset was requested for your Hasnet PrintHub admin account.\n"
            f"Open this link to set a new password:\n{reset_link}\n\n"
            f"This link expires in {settings.admin_password_reset_token_minutes} minutes.\n"
            "If you did not request this change, ignore this message."
        )
    )

    with smtplib.SMTP(host=smtp_host, port=settings.smtp_port, timeout=20) as smtp:
        if settings.smtp_use_tls:
            smtp.starttls()
        if settings.smtp_username:
            smtp.login(settings.smtp_username, settings.smtp_password)
        smtp.send_message(message)
    return True


def ensure_bootstrap_super_admin(db: Session) -> AdminUser:
    email = _normalize_email(settings.admin_bootstrap_email)
    if not email:
        raise AdminAuthError("ADMIN_BOOTSTRAP_EMAIL is required.")

    existing = db.execute(select(AdminUser).where(AdminUser.email == email)).scalar_one_or_none()
    if existing is not None:
        return existing

    password = str(settings.admin_bootstrap_password or "").strip()
    if len(password) < 8:
        raise AdminAuthError("ADMIN_BOOTSTRAP_PASSWORD must be at least 8 characters.")

    full_name = str(settings.admin_bootstrap_name or "Super Admin").strip() or "Super Admin"
    user = AdminUser(
        email=email,
        full_name=full_name,
        role="super_admin",
        is_active=True,
        password_hash=get_password_hash(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_admin_user(*, db: Session, email: str, password: str) -> AdminUser | None:
    ensure_bootstrap_super_admin(db)
    normalized_email = _normalize_email(email)
    if not normalized_email:
        return None
    user = db.execute(select(AdminUser).where(AdminUser.email == normalized_email)).scalar_one_or_none()
    if user is None or not user.is_active:
        return None
    if not verify_password(password, user.password_hash):
        return None
    user.last_login_at = _now_utc()
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def issue_admin_access_token(*, user: AdminUser) -> str:
    return create_access_token(subject=str(user.email))


def decode_admin_access_token(token: str) -> str:
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=["HS256"])
    except JWTError as exc:
        raise AdminAuthError("Invalid or expired access token.") from exc
    subject = str(payload.get("sub") or "").strip().lower()
    if not subject:
        raise AdminAuthError("Access token subject is missing.")
    return subject


def get_admin_user_by_email(*, db: Session, email: str) -> AdminUser | None:
    normalized_email = _normalize_email(email)
    if not normalized_email:
        return None
    return db.execute(select(AdminUser).where(AdminUser.email == normalized_email)).scalar_one_or_none()


def list_admin_users(*, db: Session) -> list[AdminUser]:
    ensure_bootstrap_super_admin(db)
    return db.execute(select(AdminUser).order_by(AdminUser.created_at.asc())).scalars().all()


def create_admin_user(
    *,
    db: Session,
    email: str,
    full_name: str,
    role: str,
    password: str,
    is_active: bool = True,
) -> AdminUser:
    ensure_bootstrap_super_admin(db)
    normalized_email = _normalize_email(email)
    normalized_role = _normalize_role(role)
    normalized_name = str(full_name or "").strip()
    if not normalized_email:
        raise AdminAuthError("email is required")
    if not normalized_name:
        raise AdminAuthError("full_name is required")
    if len(password) < 8:
        raise AdminAuthError("password must be at least 8 characters")

    existing = db.execute(select(AdminUser).where(AdminUser.email == normalized_email)).scalar_one_or_none()
    if existing is not None:
        raise AdminAuthError("An admin user with this email already exists.")

    user = AdminUser(
        email=normalized_email,
        full_name=normalized_name,
        role=normalized_role,
        is_active=bool(is_active),
        password_hash=get_password_hash(password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def update_admin_user(
    *,
    db: Session,
    user_id: UUID,
    full_name: str | None = None,
    role: str | None = None,
    is_active: bool | None = None,
    new_password: str | None = None,
) -> AdminUser:
    ensure_bootstrap_super_admin(db)
    user = db.get(AdminUser, user_id)
    if user is None:
        raise AdminAuthError("Admin user not found.")

    if full_name is not None:
        normalized_name = str(full_name or "").strip()
        if not normalized_name:
            raise AdminAuthError("full_name cannot be empty")
        user.full_name = normalized_name

    if role is not None:
        user.role = _normalize_role(role)

    if is_active is not None:
        user.is_active = bool(is_active)

    if new_password is not None:
        raw = str(new_password or "")
        if len(raw) < 8:
            raise AdminAuthError("password must be at least 8 characters")
        user.password_hash = get_password_hash(raw)

    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def issue_password_reset(*, db: Session, email: str, request_base_url: str | None = None) -> PasswordResetIssueResult:
    ensure_bootstrap_super_admin(db)
    normalized_email = _normalize_email(email)
    user = get_admin_user_by_email(db=db, email=normalized_email) if normalized_email else None
    if user is None:
        return PasswordResetIssueResult(delivery="silent")

    raw_token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(raw_token)
    expires_at = _now_utc() + timedelta(minutes=settings.admin_password_reset_token_minutes)

    store = _read_reset_store()
    items = []
    for item in store.get("items", []):
        if not isinstance(item, dict):
            continue
        if str(item.get("email") or "").strip().lower() != normalized_email:
            items.append(item)
            continue
        if bool(item.get("used")):
            items.append(item)
            continue
        item_expiry = _parse_dt(item.get("expires_at"))
        if item_expiry is not None and item_expiry > _now_utc():
            items.append(item)
    items.append(
        {
            "email": normalized_email,
            "token_hash": token_hash,
            "created_at": _serialize_dt(_now_utc()),
            "expires_at": _serialize_dt(expires_at),
            "used": False,
        }
    )
    _write_reset_store({"items": items})

    base = str(settings.admin_password_reset_url_base or "").strip()
    if not base:
        base = str(request_base_url or "").rstrip("/")
    if base:
        reset_link = f"{base}/admin-app/?mode=reset&token={raw_token}"
    else:
        reset_link = f"admin-app/?mode=reset&token={raw_token}"

    delivered = False
    try:
        delivered = _send_reset_email(recipient=normalized_email, full_name=user.full_name, reset_link=reset_link)
    except Exception:
        delivered = False

    if delivered:
        return PasswordResetIssueResult(delivery="email")
    return PasswordResetIssueResult(delivery="local_preview", preview_link=reset_link)


def consume_password_reset(*, db: Session, token: str, new_password: str) -> None:
    ensure_bootstrap_super_admin(db)
    raw_token = str(token or "").strip()
    if not raw_token:
        raise AdminAuthError("Reset token is required.")
    if len(str(new_password or "")) < 8:
        raise AdminAuthError("Password must be at least 8 characters.")

    token_hash = _hash_reset_token(raw_token)
    now_utc = _now_utc()
    store = _read_reset_store()
    items = []
    matched_email = None

    for item in store.get("items", []):
        if not isinstance(item, dict):
            continue
        entry_hash = str(item.get("token_hash") or "").strip()
        used = bool(item.get("used"))
        expires_at = _parse_dt(item.get("expires_at"))
        if expires_at is None or expires_at <= now_utc:
            continue
        if used:
            items.append(item)
            continue

        if entry_hash == token_hash and matched_email is None:
            matched_email = _normalize_email(str(item.get("email") or ""))
            item["used"] = True
            items.append(item)
            continue

        items.append(item)

    if not matched_email:
        _write_reset_store({"items": items})
        raise AdminAuthError("Reset token is invalid or expired.")

    user = get_admin_user_by_email(db=db, email=matched_email)
    if user is None:
        _write_reset_store({"items": items})
        raise AdminAuthError("Admin user for this token was not found.")

    user.password_hash = get_password_hash(str(new_password))
    user.is_active = True
    db.add(user)
    db.commit()

    _write_reset_store({"items": items})
