from typing import Protocol
from uuid import UUID

from app.models.store import Store
from app.services.store import StoreNotFoundError


class StoreLookupProtocol(Protocol):
    async def get_by_id_and_owner_id(
        self,
        store_id: UUID,
        owner_id: UUID,
    ) -> Store | None: ...


class StoreAccessService:
    def __init__(self, store_repository: StoreLookupProtocol) -> None:
        """매장 권한 판단에 사용할 저장소를 받습니다."""
        self._store_repository = store_repository

    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        """사용자가 매장 소유자가 아니면 예외를 발생시킵니다."""
        store = await self._store_repository.get_by_id_and_owner_id(
            store_id,
            user_id,
        )
        if store is None:
            raise StoreNotFoundError

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        """사용자가 매장 구성원이 아니면 예외를 발생시킵니다."""
        # TODO: 멤버십 구현 후 알바생도 통과하도록 Membership으로 확인합니다.
        await self.ensure_owner(store_id, user_id)
