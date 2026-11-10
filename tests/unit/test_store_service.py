from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.models.business_verification import BusinessVerification
from app.models.store import Store
from app.schemas.store import StoreCreateRequest, StoreUpdateRequest
from app.services.store import (
    BusinessVerificationRequiredError,
    StoreNotFoundError,
    StoreService,
)


class FakeStoreRepository:
    def __init__(self, stores: list[Store] | None = None) -> None:
        self.stores = stores or []

    async def create(self, store: Store) -> Store:
        store.id = uuid4()
        self.stores.append(store)
        return store

    async def list_by_owner_id(self, owner_id: UUID) -> list[Store]:
        return [
            store
            for store in self.stores
            if store.owner_id == owner_id and store.deleted_at is None
        ]

    async def get_by_id_and_owner_id(
        self,
        store_id: UUID,
        owner_id: UUID,
    ) -> Store | None:
        return next(
            (
                store
                for store in self.stores
                if store.id == store_id
                and store.owner_id == owner_id
                and store.deleted_at is None
            ),
            None,
        )

    async def save(self, store: Store) -> Store:
        return store


class FakeBusinessVerificationRepository:
    def __init__(
        self,
        verifications: list[BusinessVerification] | None = None,
    ) -> None:
        self.verifications = verifications or []

    async def get_by_id_and_requester_id(
        self,
        verification_id: int,
        requester_id: UUID,
    ) -> BusinessVerification | None:
        return next(
            (
                verification
                for verification in self.verifications
                if verification.id == verification_id
                and verification.requester_id == requester_id
            ),
            None,
        )


def make_store(owner_id: UUID, **overrides: object) -> Store:
    values: dict[str, object] = {
        "id": uuid4(),
        "owner_id": owner_id,
        "name": "우왕 카페",
        "address": "서울특별시 강남구",
        "business_verification_id": None,
        "photo_url": None,
        "payday": None,
        "business_size": None,
    }
    values.update(overrides)
    return Store(**values)


def make_verification(
    requester_id: UUID,
    *,
    verification_id: int = 101,
    status: str = "VERIFIED",
) -> BusinessVerification:
    return BusinessVerification(
        id=verification_id,
        requester_id=requester_id,
        business_registration_number="1234567890",
        owner_name="홍길동",
        business_start_date=date(2026, 1, 15),
        status=status,
        provider_message="확인 결과",
    )


def make_service(
    repository: FakeStoreRepository,
    verifications: list[BusinessVerification] | None = None,
) -> StoreService:
    return StoreService(
        repository,
        FakeBusinessVerificationRepository(verifications),
    )


@pytest.mark.asyncio
async def test_create_store_assigns_authenticated_owner() -> None:
    owner_id = uuid4()
    repository = FakeStoreRepository()
    request = StoreCreateRequest(
        name="우왕 카페",
        address="서울특별시 강남구",
        businessVerificationId=101,
        payday=25,
        businessSize="FIVE_OR_MORE",
    )

    store = await make_service(
        repository,
        [make_verification(owner_id)],
    ).create(owner_id, request)

    assert store.owner_id == owner_id
    assert store.business_verification_id == 101
    assert store.payday == 25
    assert store.business_size == "FIVE_OR_MORE"
    assert repository.stores == [store]


@pytest.mark.asyncio
@pytest.mark.parametrize("status", ["INVALID", None])
async def test_create_store_requires_verified_business(
    status: str | None,
) -> None:
    owner_id = uuid4()
    repository = FakeStoreRepository()
    verifications = (
        [] if status is None else [make_verification(owner_id, status=status)]
    )
    service = make_service(repository, verifications)
    request = StoreCreateRequest(
        name="우왕 카페",
        address="서울특별시 강남구",
        businessVerificationId=101,
    )

    with pytest.raises(BusinessVerificationRequiredError):
        await service.create(owner_id, request)

    assert repository.stores == []


@pytest.mark.asyncio
async def test_create_store_rejects_another_users_verification() -> None:
    owner_id = uuid4()
    service = make_service(
        FakeStoreRepository(),
        [make_verification(uuid4())],
    )
    request = StoreCreateRequest(
        name="우왕 카페",
        address="서울특별시 강남구",
        businessVerificationId=101,
    )

    with pytest.raises(BusinessVerificationRequiredError):
        await service.create(owner_id, request)


@pytest.mark.asyncio
async def test_list_stores_returns_only_active_owner_stores() -> None:
    owner_id = uuid4()
    active = make_store(owner_id)
    deleted = make_store(owner_id, deleted_at=datetime.now(UTC))
    another_owner = make_store(uuid4())
    service = make_service(FakeStoreRepository([active, deleted, another_owner]))

    stores = await service.list_for_owner(owner_id)

    assert stores == [active]


@pytest.mark.asyncio
async def test_get_store_rejects_another_owner() -> None:
    owner_id = uuid4()
    store = make_store(owner_id)
    service = make_service(FakeStoreRepository([store]))

    with pytest.raises(StoreNotFoundError):
        await service.get_for_owner(store.id, uuid4())


@pytest.mark.asyncio
async def test_update_store_changes_only_requested_fields() -> None:
    owner_id = uuid4()
    store = make_store(
        owner_id,
        address="기존 주소",
        photo_url="https://example.com/old.jpg",
    )
    service = make_service(FakeStoreRepository([store]))

    updated = await service.update(
        store.id,
        owner_id,
        StoreUpdateRequest(
            name="수정한 매장",
            photoUrl=None,
            payday=31,
            businessSize="UNDER_FIVE",
        ),
    )

    assert updated.name == "수정한 매장"
    assert updated.address == "기존 주소"
    assert updated.photo_url is None
    assert updated.payday == 31
    assert updated.business_size == "UNDER_FIVE"


@pytest.mark.asyncio
async def test_update_store_validates_changed_business_verification() -> None:
    owner_id = uuid4()
    store = make_store(owner_id, business_verification_id=101)
    service = make_service(
        FakeStoreRepository([store]),
        [make_verification(owner_id, verification_id=202)],
    )

    updated = await service.update(
        store.id,
        owner_id,
        StoreUpdateRequest(businessVerificationId=202),
    )

    assert updated.business_verification_id == 202


@pytest.mark.asyncio
async def test_delete_store_sets_soft_delete_timestamp() -> None:
    owner_id = uuid4()
    store = make_store(owner_id)
    service = make_service(FakeStoreRepository([store]))

    await service.delete(store.id, owner_id)

    assert store.deleted_at is not None
    with pytest.raises(StoreNotFoundError):
        await service.get_for_owner(store.id, owner_id)
