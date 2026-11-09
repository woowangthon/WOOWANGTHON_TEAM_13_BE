from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.models.invitation import Invitation
from app.models.membership import Membership
from app.models.store import Store
from app.services.membership import (
    MemberAlreadyLeftError,
    MemberNotFoundError,
    MembershipService,
    PendingMember,
    WageBelowMinimumError,
)


class FakeMembershipRepository:
    def __init__(self, membership: Membership | None = None) -> None:
        self.membership = membership
        self.invitation_id = uuid4()

    async def list_store_roles_for_user(
        self,
        user_id: UUID,
    ) -> list[tuple[Store, str, str, UUID | None, str | None, datetime]]:
        return []

    async def list_by_store_id(
        self,
        store_id: UUID,
    ) -> list[tuple[Membership, UUID | None]]:
        if self.membership is None or self.membership.store_id != store_id:
            return []
        return [(self.membership, self.invitation_id)]

    async def list_available_invitations_by_store_id(
        self,
        store_id: UUID,
    ) -> list[Invitation]:
        return []

    async def get_by_id_and_store_id(
        self,
        member_id: UUID,
        store_id: UUID,
    ) -> tuple[Membership, UUID | None] | None:
        if (
            self.membership is not None
            and self.membership.id == member_id
            and self.membership.store_id == store_id
        ):
            return self.membership, self.invitation_id
        return None

    async def leave(
        self,
        membership: Membership,
        left_at: datetime,
    ) -> Membership:
        membership.left_at = left_at
        return membership

    async def update(self, membership: Membership) -> Membership:
        return membership


def make_membership() -> Membership:
    return Membership(
        id=uuid4(),
        store_id=uuid4(),
        user_id=uuid4(),
        role="staff",
        staff_name="지은",
        hourly_wage=10_320,
        tax_type="none",
        joined_at=datetime.now(UTC),
    )


@pytest.mark.asyncio
async def test_list_user_stores_maps_summary_and_detail_fields() -> None:
    joined_at = datetime(2026, 11, 3, 13, 40, tzinfo=UTC)
    store = Store(
        id=uuid4(),
        owner_id=uuid4(),
        name="우왕 카페",
        address="서울 마포구 와우산로 1",
        photo_url="https://example.com/store.jpg",
    )
    member_id = uuid4()

    class StoreRepository(FakeMembershipRepository):
        async def list_store_roles_for_user(
            self,
            user_id: UUID,
        ) -> list[tuple[Store, str, str, UUID | None, str | None, datetime]]:
            return [
                (
                    store,
                    "staff",
                    "박 사장님",
                    member_id,
                    "지은",
                    joined_at,
                )
            ]

    service = MembershipService(StoreRepository())

    summaries = await service.list_store_summaries(uuid4())
    details = await service.list_store_details(uuid4())

    assert summaries[0].model_dump(by_alias=True) == {
        "storeId": store.id,
        "storeName": "우왕 카페",
        "role": "staff",
        "ownerName": "박 사장님",
        "staffName": "지은",
        "photoUrl": "https://example.com/store.jpg",
    }
    assert details[0].model_dump(by_alias=True) == {
        "storeId": store.id,
        "name": "우왕 카페",
        "kind": None,
        "address": "서울 마포구 와우산로 1",
        "ownerName": "박 사장님",
        "role": "staff",
        "memberId": member_id,
        "staffName": "지은",
        "photoUrl": "https://example.com/store.jpg",
        "theme": None,
        "joinedAt": joined_at,
    }


@pytest.mark.asyncio
async def test_get_member_rejects_other_store_member() -> None:
    membership = make_membership()
    service = MembershipService(FakeMembershipRepository(membership))

    with pytest.raises(MemberNotFoundError):
        await service.get_member(uuid4(), membership.id)


@pytest.mark.asyncio
async def test_leave_soft_deletes_member() -> None:
    membership = make_membership()
    service = MembershipService(FakeMembershipRepository(membership))

    result = await service.leave(membership.store_id, membership.id)

    assert result.left_at is not None


@pytest.mark.asyncio
async def test_leave_rejects_already_left_member() -> None:
    membership = make_membership()
    membership.left_at = datetime.now(UTC)
    service = MembershipService(FakeMembershipRepository(membership))

    with pytest.raises(MemberAlreadyLeftError):
        await service.leave(membership.store_id, membership.id)


@pytest.mark.asyncio
async def test_update_hourly_wage_updates_active_member() -> None:
    membership = make_membership()
    service = MembershipService(FakeMembershipRepository(membership))

    updated = await service.update_hourly_wage(
        membership.store_id,
        membership.id,
        12_000,
    )

    assert updated.hourly_wage == 12_000
    assert updated.updated_at is not None


@pytest.mark.asyncio
async def test_update_hourly_wage_rejects_below_minimum() -> None:
    membership = make_membership()
    service = MembershipService(FakeMembershipRepository(membership))

    with pytest.raises(WageBelowMinimumError):
        await service.update_hourly_wage(
            membership.store_id,
            membership.id,
            10_319,
        )


@pytest.mark.asyncio
async def test_list_members_includes_available_invitation() -> None:
    membership = make_membership()
    invitation = Invitation(
        id=uuid4(),
        store_id=membership.store_id,
        created_by_user_id=uuid4(),
        code="M8R4TW",
        staff_name="도윤",
        hourly_wage=11_000,
        created_at=membership.joined_at + timedelta(seconds=1),
    )

    class RosterRepository(FakeMembershipRepository):
        async def list_available_invitations_by_store_id(
            self,
            store_id: UUID,
        ) -> list[Invitation]:
            return [invitation]

    entries = await MembershipService(
        RosterRepository(membership)
    ).list_members(membership.store_id)

    assert isinstance(entries[0], PendingMember)
    assert entries[0].invitation.id == invitation.id
