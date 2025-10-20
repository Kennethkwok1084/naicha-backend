from __future__ import annotations

import pytest
from app.api.dependencies import auth as auth_dependencies
from app.core.security import TokenScope, create_access_token, hash_password
from app.models.accounts import Admin, User
from fastapi import HTTPException
from fastapi.security import HTTPAuthorizationCredentials


def _credential(token: str) -> HTTPAuthorizationCredentials:
    return HTTPAuthorizationCredentials(scheme="Bearer", credentials=token)


@pytest.mark.asyncio
async def test_get_current_admin_requires_header(db_session) -> None:
    with pytest.raises(HTTPException) as exc:
        await auth_dependencies.get_current_admin(credentials=None, session=db_session)

    assert exc.value.status_code == 401
    assert exc.value.detail == "Authorization header missing."


@pytest.mark.asyncio
async def test_get_current_admin_rejects_non_admin_scope(db_session) -> None:
    token = create_access_token(subject="1", scope=TokenScope.USER)

    with pytest.raises(HTTPException) as exc:
        await auth_dependencies.get_current_admin(
            credentials=_credential(token),
            session=db_session,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Insufficient scope for admin resource."


@pytest.mark.asyncio
async def test_get_current_admin_validates_subject_and_existence(db_session) -> None:
    token = create_access_token(subject="invalid-int", scope=TokenScope.ADMIN)

    with pytest.raises(HTTPException) as exc:
        await auth_dependencies.get_current_admin(
            credentials=_credential(token),
            session=db_session,
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token subject."

    real_token = create_access_token(subject="99", scope=TokenScope.ADMIN)
    with pytest.raises(HTTPException) as exc_not_found:
        await auth_dependencies.get_current_admin(
            credentials=_credential(real_token),
            session=db_session,
        )

    assert exc_not_found.value.status_code == 401
    assert exc_not_found.value.detail == "Admin not found or inactive."


@pytest.mark.asyncio
async def test_get_current_admin_returns_admin(db_session) -> None:
    admin = Admin(
        admin_id=1,
        username="root",
        password_hash=hash_password("secret"),
        role="admin",
    )
    db_session.add(admin)
    await db_session.flush()

    token = create_access_token(subject=str(admin.admin_id), scope=TokenScope.ADMIN)
    result = await auth_dependencies.get_current_admin(
        credentials=_credential(token),
        session=db_session,
    )

    assert result.admin_id == admin.admin_id
    assert result.username == "root"


@pytest.mark.asyncio
async def test_get_current_admin_invalid_token_format(db_session) -> None:
    bad_token = "invalid.jwt.token"

    with pytest.raises(HTTPException) as exc:
        await auth_dependencies.get_current_admin(
            credentials=_credential(bad_token),
            session=db_session,
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token invalid"


@pytest.mark.asyncio
async def test_get_current_user_rejects_non_user_scope(db_session) -> None:
    token = create_access_token(subject="2", scope=TokenScope.ADMIN)

    with pytest.raises(HTTPException) as exc:
        await auth_dependencies.get_current_user(
            credentials=_credential(token),
            session=db_session,
        )

    assert exc.value.status_code == 403
    assert exc.value.detail == "Insufficient scope for user resource."


@pytest.mark.asyncio
async def test_get_current_user_validates_subject_and_existence(db_session) -> None:
    token = create_access_token(subject="bad", scope=TokenScope.USER)

    with pytest.raises(HTTPException) as exc:
        await auth_dependencies.get_current_user(
            credentials=_credential(token),
            session=db_session,
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Invalid token subject."

    user_token = create_access_token(subject="777", scope=TokenScope.USER)
    with pytest.raises(HTTPException) as exc_not_found:
        await auth_dependencies.get_current_user(
            credentials=_credential(user_token),
            session=db_session,
        )

    assert exc_not_found.value.status_code == 401
    assert exc_not_found.value.detail == "User not found or inactive."


@pytest.mark.asyncio
async def test_get_current_user_returns_user(db_session) -> None:
    user = User(user_id=321, open_id="openid-321")
    db_session.add(user)
    await db_session.flush()

    token = create_access_token(subject=str(user.user_id), scope=TokenScope.USER)
    result = await auth_dependencies.get_current_user(
        credentials=_credential(token),
        session=db_session,
    )

    assert result.user_id == user.user_id
    assert result.open_id == "openid-321"


@pytest.mark.asyncio
async def test_get_current_user_invalid_token_format(db_session) -> None:
    bad_token = "invalid.jwt.token"

    with pytest.raises(HTTPException) as exc:
        await auth_dependencies.get_current_user(
            credentials=_credential(bad_token),
            session=db_session,
        )

    assert exc.value.status_code == 401
    assert exc.value.detail == "Token invalid"
