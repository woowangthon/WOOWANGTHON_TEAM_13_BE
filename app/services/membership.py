from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Literal, Protocol
from uuid import UUID

from app.models.invitation import Invitation
from app.models.membership import Membership
from app.models.store import Store
from app.schemas.invitation import MINIMUM_HOURLY_WAGE_2026
from app.schemas.membership import TaxType
from app.schemas.user import MyStoreDetail, StoreSummary

UserStoreRecord = tuple[
    Store,
    Literal["owner", "staff"],
    str,
    UUID | None,
    str | None,
    datetime,
]


class MemberNotFoundError(Exception):
    pass


class MemberAlreadyLeftError(Exception):
    pass


class WageBelowMinimumError(Exception):
    pass


@dataclass(frozen=True, slots=True)
class MemberWithInvitation:
    membership: Membership
    invitation_id: UUID | None


@dataclass(frozen=True, slots=True)
class PendingMember:
    invitation: Invitation


MemberListEntry = MemberWithInvitation | PendingMember


class MembershipRepositoryProtocol(Protocol):
    async def list_store_roles_for_user(
        self,
        user_id: UUID,
    ) -> list[UserStoreRecord]: ...

    async def list_by_store_id(
        self,
        store_id: UUID,
    ) -> list[tuple[Membership, UUID | None]]: ...

    async def list_available_invitations_by_store_id(
        self,
        store_id: UUID,
    ) -> list[Invitation]: ...

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

    async def update(self, membership: Membership) -> Membership: ...


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
                owner_name=owner_name,
                staff_name=staff_name,
                photo_url=store.photo_url,
            )
            for store, role, owner_name, _, staff_name, _ in stores
        ]

    async def list_store_details(self, user_id: UUID) -> list[MyStoreDetail]:
        stores = await self._repository.list_store_roles_for_user(user_id)
        return [
            MyStoreDetail(
                store_id=store.id,
                name=store.name,
                address=store.address,
                owner_name=owner_name,
                role=role,
                member_id=member_id,
                staff_name=staff_name,
                photo_url=store.photo_url,
                joined_at=joined_at,
            )
            for (
                store,
                role,
                owner_name,
                member_id,
                staff_name,
                joined_at,
            ) in stores
        ]

    async def list_members(self, store_id: UUID) -> list[MemberListEntry]:
        members = await self._repository.list_by_store_id(store_id)
        entries: list[MemberListEntry] = [
            MemberWithInvitation(membership, invitation_id)
            for membership, invitation_id in members
        ]
        invitations = (
            await self._repository.list_available_invitations_by_store_id(
                store_id
            )
        )
        entries.extend(PendingMember(invitation) for invitation in invitations)
        return sorted(
            entries,
            key=lambda entry: (
                entry.invitation.created_at
                if isinstance(entry, PendingMember)
                else entry.membership.joined_at
            ),
            reverse=True,
        )

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

    async def update_hourly_wage(
        self,
        store_id: UUID,
        member_id: UUID,
        hourly_wage: int,
    ) -> Membership:
        if hourly_wage < MINIMUM_HOURLY_WAGE_2026:
            raise WageBelowMinimumError
        member = await self.get_member(store_id, member_id)
        membership = member.membership
        if membership.left_at is not None:
            raise MemberAlreadyLeftError
        membership.hourly_wage = hourly_wage
        membership.updated_at = datetime.now(UTC)
        return await self._repository.update(membership)

    async def update_tax_type(
        self,
        store_id: UUID,
        member_id: UUID,
        tax_type: TaxType,
    ) -> Membership:
        member = await self.get_member(store_id, member_id)
        membership = member.membership
        if membership.left_at is not None:
            raise MemberAlreadyLeftError
        membership.tax_type = tax_type
        membership.updated_at = datetime.now(UTC)
        return await self._repository.update(membership)
