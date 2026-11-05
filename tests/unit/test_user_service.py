from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.auth import AuthenticatedUser
from app.models.user import User
from app.services.user import InactiveUserError, UserService


class FakeUserRepository:
    def __init__(self, user: User | None = None) -> None:
        self.user = user

    async def get_by_auth_user_id(
        self,
        auth_user_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        if self.user is None or self.user.auth_user_id != auth_user_id:
            return None
        if not include_deleted and self.user.deleted_at is not None:
            return None
        return self.user

    async def create(self, user: User) -> User:
        user.id = uuid4()
        self.user = user
        return user

    async def save(self, user: User) -> User:
        self.user = user
        return user


def identity(**claim_overrides: Any) -> AuthenticatedUser:
    claims: dict[str, Any] = {
        "app_metadata": {"provider": "kakao"},
        "user_metadata": {"nickname": "우왕이"},
    }
    claims.update(claim_overrides)
    return AuthenticatedUser(
        id=uuid4(),
        email=None,
        role="authenticated",
        claims=claims,
    )


@pytest.mark.asyncio
async def test_first_request_creates_application_user() -> None:
    auth_user = identity()
    repository = FakeUserRepository()

    user = await UserService(repository).get_or_create(auth_user)

    assert repository.user is user
    assert user.auth_user_id == auth_user.id
    assert user.nickname == "우왕이"
    assert user.email is None
    assert user.provider == "kakao"


@pytest.mark.asyncio
async def test_existing_user_is_returned_without_overwriting_profile() -> None:
    auth_user = identity()
    existing = User(
        id=uuid4(),
        auth_user_id=auth_user.id,
        nickname="수정한 닉네임",
        email="saved@example.com",
        provider="kakao",
    )

    user = await UserService(FakeUserRepository(existing)).get_or_create(
        auth_user
    )

    assert user is existing
    assert user.nickname == "수정한 닉네임"
    assert user.email == "saved@example.com"


@pytest.mark.asyncio
async def test_update_nickname_creates_user_when_needed() -> None:
    repository = FakeUserRepository()
    auth_user = identity()

    user = await UserService(repository).update_nickname(auth_user, "새 이름")

    assert user.nickname == "새 이름"
    assert repository.user is user


@pytest.mark.asyncio
async def test_withdraw_redacts_profile_and_keeps_auth_tombstone() -> None:
    auth_user = identity()
    existing = User(
        id=uuid4(),
        auth_user_id=auth_user.id,
        nickname="기존 이름",
        email="user@example.com",
        provider="google",
    )
    repository = FakeUserRepository(existing)
    service = UserService(repository)

    await service.withdraw(auth_user)

    assert existing.nickname == "탈퇴한 사용자"
    assert existing.email is None
    assert existing.deleted_at is not None
    with pytest.raises(InactiveUserError):
        await service.get_or_create(auth_user)
