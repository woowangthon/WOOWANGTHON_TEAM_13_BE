from dataclasses import dataclass
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


@dataclass(frozen=True, slots=True)
class MemberWithInvitation:
    membership: Membership
    invitation_id: UUID | None


class MembershipRepositoryProtocol(Protocol):
    async def list_store_roles_for_user(
        self,
        user_id: UUID,
    ) -> list[tuple[Store, str]]: ...

    async def list_by_store_id(
        self,
        store_id: UUID,
    ) -> list[tuple[Membership, UUID | None]]: ...

    async def get_by_id_and_store_id(
        self,
        member_id: UUID,
        store_id: UUID,
    ) -> tuple[Membership, UUID | None] | None: ...

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

    async def list_members(self, store_id: UUID) -> list[MemberWithInvitation]:
        members = await self._repository.list_by_store_id(store_id)
        return [
            MemberWithInvitation(membership, invitation_id)
            for membership, invitation_id in members
        ]

    async def get_member(
        self,
        store_id: UUID,
        member_id: UUID,
    ) -> MemberWithInvitation:
        member = await self._repository.get_by_id_and_store_id(
            member_id,
            store_id,
        )
        if member is None:
            raise MemberNotFoundError
        membership, invitation_id = member
        return MemberWithInvitation(membership, invitation_id)

    async def leave(self, store_id: UUID, member_id: UUID) -> Membership:
        member = await self.get_member(store_id, member_id)
        membership = member.membership
        if membership.left_at is not None:
            raise MemberAlreadyLeftError
        return await self._repository.leave(membership, datetime.now(UTC))
