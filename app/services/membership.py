from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from app.models.membership import Membership
from app.models.store import Store
from app.schemas.user import StoreSummary


class MemberNotFoundError(Exception):
    pass


class MemberAlreadyLeftError(Exception):
    pass


class MembershipRepositoryProtocol(Protocol):
    async def list_store_roles_for_user(
        self,
        user_id: UUID,
    ) -> list[tuple[Store, str]]: ...

    async def list_by_store_id(self, store_id: UUID) -> list[Membership]: ...

    async def get_by_id_and_store_id(
        self,
        member_id: UUID,
        store_id: UUID,
    ) -> Membership | None: ...

    async def leave(
        self,
        membership: Membership,
        left_at: datetime,
    ) -> Membership: ...


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

    async def list_members(self, store_id: UUID) -> list[Membership]:
        return await self._repository.list_by_store_id(store_id)

    async def get_member(
        self,
        store_id: UUID,
        member_id: UUID,
    ) -> Membership:
        membership = await self._repository.get_by_id_and_store_id(
            member_id,
            store_id,
        )
        if membership is None:
            raise MemberNotFoundError
        return membership

    async def leave(self, store_id: UUID, member_id: UUID) -> Membership:
        membership = await self.get_member(store_id, member_id)
        if membership.left_at is not None:
            raise MemberAlreadyLeftError
        return await self._repository.leave(membership, datetime.now(UTC))
