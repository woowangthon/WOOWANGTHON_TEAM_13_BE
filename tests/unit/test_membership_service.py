from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.models.membership import Membership
from app.services.membership import (
    MemberAlreadyLeftError,
    MemberNotFoundError,
    MembershipService,
)


class FakeMembershipRepository:
    def __init__(self, membership: Membership | None = None) -> None:
        self.membership = membership
        self.invitation_id = uuid4()

    async def list_store_roles_for_user(self, user_id: UUID) -> list[object]:
        return []

    async def list_by_store_id(
        self,
        store_id: UUID,
    ) -> list[tuple[Membership, UUID | None]]:
        if self.membership is None or self.membership.store_id != store_id:
            return []
        return [(self.membership, self.invitation_id)]

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


def make_membership() -> Membership:
    return Membership(
        id=uuid4(),
        store_id=uuid4(),
        user_id=uuid4(),
        role="staff",
        staff_name="지은",
        hourly_wage=10_320,
        joined_at=datetime.now(UTC),
    )


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
