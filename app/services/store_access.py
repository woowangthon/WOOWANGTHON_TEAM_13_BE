from typing import Protocol
from uuid import UUID

from app.models.membership import Membership
from app.models.store import Store
from app.services.store import StoreNotFoundError


class StoreAccessForbiddenError(Exception):
    """구성원이 사장님 전용 기능을 요청했을 때 발생합니다."""


class StoreLookupProtocol(Protocol):
    async def get_by_id_and_owner_id(
        self,
        store_id: UUID,
        owner_id: UUID,
    ) -> Store | None: ...


class MembershipLookupProtocol(Protocol):
    async def get_active_by_store_and_user_id(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> Membership | None: ...


class StoreAccessProtocol(Protocol):
    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None: ...

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None: ...


class StoreAccessService:
    def __init__(
        self,
        store_repository: StoreLookupProtocol,
        membership_repository: MembershipLookupProtocol,
    ) -> None:
        """매장 권한 판단에 사용할 저장소를 받습니다."""
        self._store_repository = store_repository
        self._membership_repository = membership_repository

    async def _is_owner(self, store_id: UUID, user_id: UUID) -> bool:
        """사용자가 삭제되지 않은 매장의 소유자인지 확인합니다."""
        store = await self._store_repository.get_by_id_and_owner_id(
            store_id,
            user_id,
        )
        return store is not None

    async def _is_active_member(self, store_id: UUID, user_id: UUID) -> bool:
        """사용자가 재직 중인 구성원인지 확인합니다."""
        membership = (
            await self._membership_repository.get_active_by_store_and_user_id(
                store_id,
                user_id,
            )
        )
        return membership is not None

    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        """구성원이면 403, 외부인이면 404에 해당하는 예외를 발생시킵니다."""
        if await self._is_owner(store_id, user_id):
            return
        if await self._is_active_member(store_id, user_id):
            raise StoreAccessForbiddenError
        raise StoreNotFoundError

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        """소유자나 재직 중인 구성원이 아니면 예외를 발생시킵니다."""
        if await self._is_owner(store_id, user_id):
            return
        if not await self._is_active_member(store_id, user_id):
            raise StoreNotFoundError
