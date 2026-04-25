from types import SimpleNamespace
from uuid import UUID

import pytest
from fastapi import HTTPException, status

from app.api.deps import require_admin_or_super_admin, require_super_admin
from app.api.routes import admin_auth as admin_auth_routes


def test_require_admin_or_super_admin_allows_admin_roles() -> None:
    assert require_admin_or_super_admin(SimpleNamespace(role="admin")).role == "admin"
    assert require_admin_or_super_admin(SimpleNamespace(role="super_admin")).role == "super_admin"


def test_require_admin_or_super_admin_blocks_technician_and_monitor() -> None:
    with pytest.raises(HTTPException) as technician_exc:
        require_admin_or_super_admin(SimpleNamespace(role="technician"))
    assert technician_exc.value.status_code == status.HTTP_403_FORBIDDEN

    with pytest.raises(HTTPException) as monitor_exc:
        require_admin_or_super_admin(SimpleNamespace(role="monitor"))
    assert monitor_exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_require_super_admin_blocks_non_super_admin() -> None:
    with pytest.raises(HTTPException) as exc:
        require_super_admin(SimpleNamespace(role="admin"))
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_admin_user_create_prevents_admin_from_creating_super_admin() -> None:
    payload = admin_auth_routes.AdminUserCreateRequest(
        email="new-admin@example.com",
        full_name="New Admin",
        role="super_admin",
        password="strongpass123",
        is_active=True,
    )
    with pytest.raises(HTTPException) as exc:
        admin_auth_routes.admin_create_user(
            payload=payload,
            current_user=SimpleNamespace(role="admin"),
            db=None,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN


def test_admin_user_update_prevents_admin_from_promoting_super_admin() -> None:
    payload = admin_auth_routes.AdminUserUpdateRequest(role="super_admin")
    with pytest.raises(HTTPException) as exc:
        admin_auth_routes.admin_update_user(
            user_id=UUID("11111111-1111-1111-1111-111111111111"),
            payload=payload,
            current_user=SimpleNamespace(role="admin"),
            db=None,  # type: ignore[arg-type]
        )
    assert exc.value.status_code == status.HTTP_403_FORBIDDEN
