from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from app.models.store import Store
from app.schemas.store import StoreCreateRequest, StoreUpdateRequest


class StoreNotFoundError(Exception):
    """소유자가 접근할 수 있는 매장을 찾지 못했을 때 발생합니다."""


class StoreRepositoryProtocol(Protocol):
    async def create(self, store: Store) -> Store: ...

    async def list_by_owner_id(self, owner_id: UUID) -> list[Store]: ...

    async def get_by_id_and_owner_id(
        self,
        store_id: UUID,
        owner_id: UUID,
    ) -> Store | None: ...

    async def save(self, store: Store) -> Store: ...


class StoreService:
    def __init__(self, repository: StoreRepositoryProtocol) -> None:
        """매장 비즈니스 로직에 사용할 저장소를 받습니다."""
        self._repository = repository

    async def create(
        self,
        owner_id: UUID,
        request: StoreCreateRequest,
    ) -> Store:
        """로그인한 사용자의 매장을 생성합니다."""
        store = Store(
            owner_id=owner_id,
            name=request.name,
            address=request.address,
            business_verification_id=request.business_verification_id,
            photo_url=request.photo_url,
        )
        return await self._repository.create(store)

    async def list_for_owner(self, owner_id: UUID) -> list[Store]:
        """로그인한 사용자가 소유한 매장 목록을 조회합니다."""
        return await self._repository.list_by_owner_id(owner_id)

    async def get_for_owner(self, store_id: UUID, owner_id: UUID) -> Store:
        """로그인한 사용자가 소유한 매장 상세 정보를 조회합니다."""
        store = await self._repository.get_by_id_and_owner_id(
            store_id,
            owner_id,
        )
        if store is None:
            raise StoreNotFoundError
        return store

    async def update(
        self,
        store_id: UUID,
        owner_id: UUID,
        request: StoreUpdateRequest,
    ) -> Store:
        """로그인한 사용자가 소유한 매장 정보를 수정합니다."""
        store = await self.get_for_owner(store_id, owner_id)
        fields: Mapping[str, Any] = request.model_dump(
            exclude_unset=True,
            by_alias=False,
        )
        for field, value in fields.items():
            setattr(store, field, value)
        return await self._repository.save(store)

    async def delete(self, store_id: UUID, owner_id: UUID) -> None:
        """로그인한 사용자가 소유한 매장을 삭제 처리합니다."""
        store = await self.get_for_owner(store_id, owner_id)
        store.deleted_at = datetime.now(UTC)
        await self._repository.save(store)
