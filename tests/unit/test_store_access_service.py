from uuid import UUID, uuid4

import pytest

from app.models.membership import Membership
from app.models.store import Store
from app.services.store import StoreNotFoundError
from app.services.store_access import (
    StoreAccessForbiddenError,
    StoreAccessService,
)

STORE_ID = uuid4()
OWNER_ID = uuid4()
STAFF_ID = uuid4()
OUTSIDER_ID = uuid4()


class FakeStoreRepository:
    async def get_by_id_and_owner_id(
        self,
        store_id: UUID,
        owner_id: UUID,
    ) -> Store | None:
        if (store_id, owner_id) == (STORE_ID, OWNER_ID):
            return Store(id=store_id, owner_id=owner_id)
        return None


class FakeMembershipRepository:
    async def get_active_by_store_and_user_id(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> Membership | None:
        if (store_id, user_id) == (STORE_ID, STAFF_ID):
            return Membership(store_id=store_id, user_id=user_id)
        return None


@pytest.fixture
def access() -> StoreAccessService:
    return StoreAccessService(FakeStoreRepository(), FakeMembershipRepository())


async def test_owner_passes_owner_and_member_checks(
    access: StoreAccessService,
) -> None:
    await access.ensure_owner(STORE_ID, OWNER_ID)
    await access.ensure_member(STORE_ID, OWNER_ID)


async def test_staff_passes_member_check(access: StoreAccessService) -> None:
    await access.ensure_member(STORE_ID, STAFF_ID)


async def test_staff_is_forbidden_from_owner_actions(
    access: StoreAccessService,
) -> None:
    with pytest.raises(StoreAccessForbiddenError):
        await access.ensure_owner(STORE_ID, STAFF_ID)


async def test_outsider_cannot_tell_the_store_exists(
    access: StoreAccessService,
) -> None:
    with pytest.raises(StoreNotFoundError):
        await access.ensure_owner(STORE_ID, OUTSIDER_ID)
    with pytest.raises(StoreNotFoundError):
        await access.ensure_member(STORE_ID, OUTSIDER_ID)


async def test_staff_of_another_store_is_an_outsider(
    access: StoreAccessService,
) -> None:
    other_store_id = uuid4()

    with pytest.raises(StoreNotFoundError):
        await access.ensure_member(other_store_id, STAFF_ID)
    with pytest.raises(StoreNotFoundError):
        await access.ensure_owner(other_store_id, STAFF_ID)
