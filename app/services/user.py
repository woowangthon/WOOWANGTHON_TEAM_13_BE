from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.core.auth import AuthenticatedUser
from app.models.user import User


class InactiveUserError(Exception):
    """탈퇴한 사용자가 서비스에 접근할 때 발생합니다."""


class UserRepositoryProtocol(Protocol):
    async def get_by_auth_user_id(
        self,
        auth_user_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> User | None: ...

    async def create(self, user: User) -> User: ...

    async def save(self, user: User) -> User: ...


class UserService:
    def __init__(self, repository: UserRepositoryProtocol) -> None:
        """사용자 비즈니스 로직에 사용할 저장소를 받습니다."""
        self._repository = repository

    async def get_or_create(self, identity: AuthenticatedUser) -> User:
        """사용자를 조회하고 최초 요청이면 새로 생성합니다."""
        user = await self._repository.get_by_auth_user_id(
            identity.id,
            include_deleted=True,
        )
        if user is not None:
            self._ensure_active(user)
            return user

        user = User(
            auth_user_id=identity.id,
            nickname=_nickname_from_claims(identity.claims, identity.email),
            email=identity.email,
            provider=_provider_from_claims(identity.claims),
        )
        try:
            return await self._repository.create(user)
        except IntegrityError:
            # A concurrent first request may have created the same mapping.
            existing = await self._repository.get_by_auth_user_id(
                identity.id,
                include_deleted=True,
            )
            if existing is None:
                raise
            self._ensure_active(existing)
            return existing

    async def update_nickname(
        self,
        identity: AuthenticatedUser,
        nickname: str,
    ) -> User:
        """현재 사용자의 닉네임을 수정합니다."""
        user = await self.get_or_create(identity)
        user.nickname = nickname
        return await self._repository.save(user)

    async def withdraw(self, identity: AuthenticatedUser) -> None:
        """현재 사용자의 프로필을 비식별화하고 탈퇴 처리합니다."""
        user = await self._repository.get_by_auth_user_id(
            identity.id,
            include_deleted=True,
        )
        if user is None or user.deleted_at is not None:
            return

        # 같은 인증 계정으로 다시 로그인하면 새 사용자로 시작하도록 연결을 끊습니다.
        user.auth_user_id = uuid4()
        user.nickname = "탈퇴한 사용자"
        user.email = None
        user.deleted_at = datetime.now(UTC)
        await self._repository.save(user)

    @staticmethod
    def _ensure_active(user: User) -> None:
        """탈퇴한 사용자이면 서비스 접근을 막습니다."""
        if user.deleted_at is not None:
            raise InactiveUserError


def _provider_from_claims(claims: Mapping[str, Any]) -> str:
    """JWT 클레임에서 로그인 제공자를 찾습니다."""
    app_metadata = claims.get("app_metadata")
    if isinstance(app_metadata, Mapping):
        provider = app_metadata.get("provider")
        if isinstance(provider, str) and provider.strip():
            return provider.strip().lower()

    identities = claims.get("identities")
    if isinstance(identities, list) and identities:
        identity = identities[0]
        if isinstance(identity, Mapping):
            provider = identity.get("provider")
            if isinstance(provider, str) and provider.strip():
                return provider.strip().lower()

    return "unknown"


def _nickname_from_claims(
    claims: Mapping[str, Any],
    email: str | None,
) -> str:
    """JWT 사용자 정보에서 최초 닉네임을 정합니다."""
    user_metadata = claims.get("user_metadata")
    if isinstance(user_metadata, Mapping):
        for key in ("nickname", "name", "full_name", "user_name"):
            value = user_metadata.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()[:50]

    if email:
        return email.split("@", maxsplit=1)[0][:50]
    return "사용자"
