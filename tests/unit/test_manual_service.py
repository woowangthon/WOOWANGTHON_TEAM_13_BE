from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.models.manual import Manual, ManualCategory
from app.schemas.manual import (
    ManualCategoryCreateRequest,
    ManualCreateRequest,
    ManualUpdateRequest,
)
from app.services.manual import (
    MANUAL_TEMPLATES,
    ManualCategoryNotFoundError,
    ManualNotFoundError,
    ManualService,
)
from app.services.store import StoreNotFoundError


class FakeManualRepository:
    def __init__(self) -> None:
        self.manuals: list[Manual] = []
        self.categories: list[ManualCategory] = []

    async def create_category(self, category: ManualCategory) -> ManualCategory:
        category.id = uuid4()
        self.categories.append(category)
        return category

    async def get_category(
        self,
        category_id: UUID,
        store_id: UUID,
    ) -> ManualCategory | None:
        return next(
            (
                category
                for category in self.categories
                if category.id == category_id and category.store_id == store_id
            ),
            None,
        )

    async def create(self, manual: Manual) -> Manual:
        manual.id = uuid4()
        self.manuals.append(manual)
        return manual

    async def list_by_store_id(self, store_id: UUID) -> list[Manual]:
        return [
            manual
            for manual in self.manuals
            if manual.store_id == store_id and manual.deleted_at is None
        ]

    async def get_by_id_and_store_id(
        self,
        manual_id: UUID,
        store_id: UUID,
    ) -> Manual | None:
        return next(
            (
                manual
                for manual in await self.list_by_store_id(store_id)
                if manual.id == manual_id
            ),
            None,
        )

    async def save(self, manual: Manual) -> Manual:
        return manual


class FakeStoreAccess:
    def __init__(self, store_id: UUID, owner_id: UUID) -> None:
        self.store_id = store_id
        self.owner_id = owner_id

    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        if store_id != self.store_id or user_id != self.owner_id:
            raise StoreNotFoundError

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        await self.ensure_owner(store_id, user_id)


STORE_ID = uuid4()
OWNER_ID = uuid4()


@pytest.fixture
def repository() -> FakeManualRepository:
    return FakeManualRepository()


@pytest.fixture
def service(repository: FakeManualRepository) -> ManualService:
    return ManualService(repository, FakeStoreAccess(STORE_ID, OWNER_ID))


def manual_request(**overrides: object) -> ManualCreateRequest:
    values: dict[str, object] = {"title": "오픈 순서", "body": "머신 예열"}
    return ManualCreateRequest.model_validate({**values, **overrides})


async def test_create_and_list_manual(service: ManualService) -> None:
    created = await service.create(STORE_ID, OWNER_ID, manual_request(icon="open"))

    assert created.store_id == STORE_ID
    assert created.icon == "open"
    assert await service.list_for_store(STORE_ID, OWNER_ID) == [created]


async def test_non_owner_cannot_create_or_read(service: ManualService) -> None:
    created = await service.create(STORE_ID, OWNER_ID, manual_request())
    stranger = uuid4()

    with pytest.raises(StoreNotFoundError):
        await service.create(STORE_ID, stranger, manual_request())
    with pytest.raises(StoreNotFoundError):
        await service.list_for_store(STORE_ID, stranger)
    with pytest.raises(StoreNotFoundError):
        await service.get(STORE_ID, created.id, stranger)


async def test_manual_from_other_store_is_not_found(
    repository: FakeManualRepository,
    service: ManualService,
) -> None:
    other = Manual(id=uuid4(), store_id=uuid4(), title="다른 매장", body="비밀")
    repository.manuals.append(other)

    with pytest.raises(ManualNotFoundError):
        await service.get(STORE_ID, other.id, OWNER_ID)


async def test_create_rejects_category_of_other_store(
    repository: FakeManualRepository,
    service: ManualService,
) -> None:
    category = ManualCategory(id=uuid4(), store_id=uuid4(), name="다른 매장")
    repository.categories.append(category)

    with pytest.raises(ManualCategoryNotFoundError):
        await service.create(
            STORE_ID,
            OWNER_ID,
            manual_request(categoryId=str(category.id)),
        )


async def test_create_with_own_category(service: ManualService) -> None:
    category = await service.create_category(
        STORE_ID,
        OWNER_ID,
        ManualCategoryCreateRequest(name="마감 업무"),
    )

    created = await service.create(
        STORE_ID,
        OWNER_ID,
        manual_request(categoryId=str(category.id)),
    )

    assert created.category_id == category.id


async def test_update_changes_only_sent_fields(service: ManualService) -> None:
    created = await service.create(STORE_ID, OWNER_ID, manual_request(icon="open"))

    updated = await service.update(
        STORE_ID,
        created.id,
        OWNER_ID,
        ManualUpdateRequest.model_validate({"title": "새 제목"}),
    )

    assert updated.title == "새 제목"
    assert updated.body == "머신 예열"
    assert updated.icon == "open"


async def test_update_can_clear_icon_and_category(service: ManualService) -> None:
    category = await service.create_category(
        STORE_ID,
        OWNER_ID,
        ManualCategoryCreateRequest(name="마감 업무"),
    )
    created = await service.create(
        STORE_ID,
        OWNER_ID,
        manual_request(icon="open", categoryId=str(category.id)),
    )

    updated = await service.update(
        STORE_ID,
        created.id,
        OWNER_ID,
        ManualUpdateRequest.model_validate({"icon": None, "categoryId": None}),
    )

    assert updated.icon is None
    assert updated.category_id is None


async def test_deleted_manual_is_hidden(service: ManualService) -> None:
    created = await service.create(STORE_ID, OWNER_ID, manual_request())

    await service.delete(STORE_ID, created.id, OWNER_ID)

    assert isinstance(created.deleted_at, datetime)
    assert created.deleted_at.tzinfo == UTC
    assert await service.list_for_store(STORE_ID, OWNER_ID) == []
    with pytest.raises(ManualNotFoundError):
        await service.get(STORE_ID, created.id, OWNER_ID)


async def test_recommend_puts_matching_templates_first(
    service: ManualService,
) -> None:
    templates = await service.recommend(STORE_ID, OWNER_ID, ["배달"])

    assert templates[0].icon == "delivery"
    assert len(templates) == len(MANUAL_TEMPLATES)


async def test_recommend_without_keywords_keeps_default_order(
    service: ManualService,
) -> None:
    templates = await service.recommend(STORE_ID, OWNER_ID, [])

    assert tuple(templates) == MANUAL_TEMPLATES
