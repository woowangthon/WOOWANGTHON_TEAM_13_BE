from typing import Any
from uuid import UUID, uuid4

import pytest

from app.core.auth import AuthenticatedUser
from app.models.user import User
from app.services.user import UserService


class FakeUserRepository:
    def __init__(self, user: User | None = None) -> None:
        self.user = user
        self.users = [] if user is None else [user]

    async def get_by_auth_user_id(
        self,
        auth_user_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        for user in self.users:
            if user.auth_user_id != auth_user_id:
                continue
            if not include_deleted and user.deleted_at is not None:
                return None
            return user
        return None

    async def create(self, user: User) -> User:
        user.id = uuid4()
        self.user = user
        self.users.append(user)
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
async def test_withdraw_redacts_profile_and_detaches_auth_identity() -> None:
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
    original_user_id = existing.id

    await service.withdraw(auth_user)

    assert existing.id == original_user_id
    assert existing.auth_user_id != auth_user.id
    assert existing.nickname == "탈퇴한 사용자"
    assert existing.email is None
    assert existing.deleted_at is not None

    recreated = await service.get_or_create(auth_user)

    assert recreated is not existing
    assert recreated.auth_user_id == auth_user.id
    assert recreated.deleted_at is None
    assert repository.users == [existing, recreated]
