from typing import Protocol
from uuid import UUID

from app.models.store import Store
from app.schemas.user import StoreSummary


class MembershipRepositoryProtocol(Protocol):
    async def list_store_roles_for_user(
        self,
        user_id: UUID,
    ) -> list[tuple[Store, str]]: ...


class MembershipService:
    def __init__(self, repository: MembershipRepositoryProtocol) -> None:
        self._repository = repository

    async def list_store_summaries(self, user_id: UUID) -> list[StoreSummary]:
        stores = await self._repository.list_store_roles_for_user(user_id)
        return [
            StoreSummary(
                store_id=store.id,
                store_name=store.name,
                role=role,
            )
            for store, role in stores
        ]
