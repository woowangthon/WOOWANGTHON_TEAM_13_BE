from collections.abc import Sequence
from uuid import UUID, uuid4

import pytest

from app.integrations.storage import StorageError
from app.models.recipe import Recipe
from app.schemas.recipe import RecipeCreateRequest, RecipeUpdateRequest
from app.services.recipe import (
    MAX_IMAGE_BYTES,
    SIGNED_URL_SECONDS,
    RecipeImage,
    RecipeImageStorageError,
    RecipeImageTooLargeError,
    RecipeImageTypeError,
    RecipeNotFoundError,
    RecipeService,
    count_categories,
    detect_image_type,
)
from app.services.store import StoreNotFoundError

JPEG = bytes.fromhex("ffd8ffe000104a464946") + b"jpeg-body"
PNG = bytes.fromhex("89504e470d0a1a0a") + b"png-body"
WEBP = b"RIFF" + bytes(4) + b"WEBPVP8 " + b"webp-body"


class FakeRecipeRepository:
    def __init__(self) -> None:
        self.recipes: list[Recipe] = []
        self.fail_on_create = False

    async def create(self, recipe: Recipe) -> Recipe:
        if self.fail_on_create:
            raise RuntimeError("db down")
        if recipe.id is None:
            recipe.id = uuid4()
        self.recipes.append(recipe)
        return recipe

    async def list_by_store_id(self, store_id: UUID) -> list[Recipe]:
        return [
            recipe
            for recipe in self.recipes
            if recipe.store_id == store_id and recipe.deleted_at is None
        ]

    async def get_by_id_and_store_id(
        self,
        recipe_id: UUID,
        store_id: UUID,
    ) -> Recipe | None:
        return next(
            (
                recipe
                for recipe in await self.list_by_store_id(store_id)
                if recipe.id == recipe_id
            ),
            None,
        )

    async def save(self, recipe: Recipe) -> Recipe:
        return recipe


class FakeStoreAccess:
    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        if store_id != STORE_ID or user_id != OWNER_ID:
            raise StoreNotFoundError

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        await self.ensure_owner(store_id, user_id)


class FakeStorage:
    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}
        self.deleted: list[str] = []
        self.signed_with: list[tuple[list[str], int]] = []
        self.fail_upload = False
        self.fail_sign = False
        self.fail_delete = False

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        if self.fail_upload:
            raise StorageError("upload failed")
        self.files[path] = (data, content_type)

    async def delete(self, paths: Sequence[str]) -> None:
        if self.fail_delete:
            raise StorageError("delete failed")
        for path in paths:
            self.files.pop(path, None)
            self.deleted.append(path)

    async def signed_urls(
        self,
        paths: Sequence[str],
        expires_in_seconds: int,
    ) -> dict[str, str]:
        if self.fail_sign:
            raise StorageError("sign failed")
        self.signed_with.append((list(paths), expires_in_seconds))
        return {path: f"https://signed/{path}" for path in paths}


STORE_ID = uuid4()
OWNER_ID = uuid4()


@pytest.fixture
def repository() -> FakeRecipeRepository:
    return FakeRecipeRepository()


@pytest.fixture
def storage() -> FakeStorage:
    return FakeStorage()


@pytest.fixture
def service(repository: FakeRecipeRepository, storage: FakeStorage) -> RecipeService:
    return RecipeService(repository, FakeStoreAccess(), storage)


def recipe_request(**overrides: object) -> RecipeCreateRequest:
    values: dict[str, object] = {
        "name": "딸기라떼",
        "category": "라떼",
        "temp": "ICE",
        "size": "16oz",
        "ingredients": [{"name": "우유", "amount": "200ml"}],
        "steps": ["딸기청 3스푼을 바닥에"],
    }
    return RecipeCreateRequest.model_validate({**values, **overrides})


async def test_create_stores_plain_json_values(service: RecipeService) -> None:
    created = await service.create(STORE_ID, OWNER_ID, recipe_request())

    assert created.store_id == STORE_ID
    assert created.ingredients == [{"name": "우유", "amount": "200ml"}]
    assert created.steps == ["딸기청 3스푼을 바닥에"]
    assert created.memo is None


async def test_non_owner_cannot_create_or_read(service: RecipeService) -> None:
    created = await service.create(STORE_ID, OWNER_ID, recipe_request())
    stranger = uuid4()

    with pytest.raises(StoreNotFoundError):
        await service.create(STORE_ID, stranger, recipe_request())
    with pytest.raises(StoreNotFoundError):
        await service.list_for_store(STORE_ID, stranger)
    with pytest.raises(StoreNotFoundError):
        await service.get(STORE_ID, created.id, stranger)


async def test_recipe_from_other_store_is_not_found(
    repository: FakeRecipeRepository,
    service: RecipeService,
) -> None:
    other = Recipe(
        id=uuid4(),
        store_id=uuid4(),
        name="다른 매장",
        category="커피",
        ingredients=[],
        steps=[],
    )
    repository.recipes.append(other)

    with pytest.raises(RecipeNotFoundError):
        await service.get(STORE_ID, other.id, OWNER_ID)


async def test_update_changes_only_sent_fields(service: RecipeService) -> None:
    created = await service.create(STORE_ID, OWNER_ID, recipe_request())

    updated = await service.update(
        STORE_ID,
        created.id,
        OWNER_ID,
        RecipeUpdateRequest.model_validate(
            {"ingredients": [{"name": "딸기청", "amount": "3스푼"}], "temp": None}
        ),
    )

    assert updated.ingredients == [{"name": "딸기청", "amount": "3스푼"}]
    assert updated.temp is None
    assert updated.name == "딸기라떼"
    assert updated.size == "16oz"


async def test_deleted_recipe_is_hidden(service: RecipeService) -> None:
    created = await service.create(STORE_ID, OWNER_ID, recipe_request())

    await service.delete(STORE_ID, created.id, OWNER_ID)

    assert await service.list_for_store(STORE_ID, OWNER_ID) == []
    with pytest.raises(RecipeNotFoundError):
        await service.get(STORE_ID, created.id, OWNER_ID)


def test_count_categories_keeps_first_seen_order() -> None:
    recipes = [
        Recipe(category="라떼"),
        Recipe(category="커피"),
        Recipe(category="라떼"),
    ]

    assert list(count_categories(recipes).items()) == [("라떼", 2), ("커피", 1)]


def test_detect_image_type_uses_file_signature() -> None:
    assert detect_image_type(JPEG) == ("image/jpeg", "jpg")
    assert detect_image_type(PNG) == ("image/png", "png")
    assert detect_image_type(WEBP) == ("image/webp", "webp")
    with pytest.raises(RecipeImageTypeError):
        detect_image_type(b"GIF89a-not-allowed")


async def test_create_uploads_both_images(
    service: RecipeService,
    storage: FakeStorage,
) -> None:
    created = await service.create(
        STORE_ID,
        OWNER_ID,
        recipe_request(),
        {"menu": RecipeImage(JPEG), "recipe": RecipeImage(PNG)},
    )

    assert created.image_path is not None
    assert created.recipe_image_path is not None
    prefix = f"stores/{STORE_ID}/recipes/{created.id}/"
    assert created.image_path.startswith(prefix + "menu-")
    assert created.image_path.endswith(".jpg")
    assert created.recipe_image_path.startswith(prefix + "recipe-")
    assert created.recipe_image_path.endswith(".png")
    assert storage.files[created.image_path] == (JPEG, "image/jpeg")
    assert storage.files[created.recipe_image_path] == (PNG, "image/png")


async def test_create_without_images_has_no_paths(
    service: RecipeService,
    storage: FakeStorage,
) -> None:
    created = await service.create(STORE_ID, OWNER_ID, recipe_request())

    assert created.image_path is None
    assert created.recipe_image_path is None
    assert storage.files == {}


async def test_create_rejects_bad_image_before_saving(
    service: RecipeService,
    repository: FakeRecipeRepository,
    storage: FakeStorage,
) -> None:
    with pytest.raises(RecipeImageTypeError):
        await service.create(
            STORE_ID,
            OWNER_ID,
            recipe_request(),
            {"menu": RecipeImage(JPEG), "recipe": RecipeImage(b"%PDF-1.7")},
        )
    with pytest.raises(RecipeImageTooLargeError):
        await service.create(
            STORE_ID,
            OWNER_ID,
            recipe_request(),
            {"menu": RecipeImage(JPEG + bytes(MAX_IMAGE_BYTES))},
        )
    with pytest.raises(RecipeImageTooLargeError):
        await service.create(
            STORE_ID, OWNER_ID, recipe_request(), {"menu": RecipeImage(b"")}
        )

    assert repository.recipes == []
    assert storage.files == {}


async def test_create_cleans_up_uploads_when_db_fails(
    service: RecipeService,
    repository: FakeRecipeRepository,
    storage: FakeStorage,
) -> None:
    repository.fail_on_create = True

    with pytest.raises(RuntimeError):
        await service.create(
            STORE_ID, OWNER_ID, recipe_request(), {"menu": RecipeImage(JPEG)}
        )

    assert storage.files == {}
    assert len(storage.deleted) == 1


async def test_create_reports_storage_failure_and_saves_nothing(
    service: RecipeService,
    repository: FakeRecipeRepository,
    storage: FakeStorage,
) -> None:
    storage.fail_upload = True

    with pytest.raises(RecipeImageStorageError):
        await service.create(
            STORE_ID, OWNER_ID, recipe_request(), {"menu": RecipeImage(JPEG)}
        )

    assert repository.recipes == []


async def test_stranger_cannot_upload(
    service: RecipeService,
    storage: FakeStorage,
) -> None:
    created = await service.create(STORE_ID, OWNER_ID, recipe_request())

    with pytest.raises(StoreNotFoundError):
        await service.set_image(
            STORE_ID, created.id, uuid4(), "menu", RecipeImage(JPEG)
        )
    assert storage.files == {}


async def test_set_image_replaces_and_deletes_previous(
    service: RecipeService,
    storage: FakeStorage,
) -> None:
    created = await service.create(
        STORE_ID, OWNER_ID, recipe_request(), {"menu": RecipeImage(JPEG)}
    )
    previous = created.image_path

    updated = await service.set_image(
        STORE_ID, created.id, OWNER_ID, "menu", RecipeImage(WEBP)
    )

    assert updated.image_path != previous
    assert updated.image_path is not None
    assert updated.image_path.endswith(".webp")
    assert previous in storage.deleted
    assert list(storage.files) == [updated.image_path]


async def test_set_image_on_missing_recipe_uploads_nothing(
    service: RecipeService,
    storage: FakeStorage,
) -> None:
    with pytest.raises(RecipeNotFoundError):
        await service.set_image(
            STORE_ID, uuid4(), OWNER_ID, "recipe", RecipeImage(JPEG)
        )
    assert storage.files == {}


async def test_remove_image_clears_only_that_slot(
    service: RecipeService,
    storage: FakeStorage,
) -> None:
    created = await service.create(
        STORE_ID,
        OWNER_ID,
        recipe_request(),
        {"menu": RecipeImage(JPEG), "recipe": RecipeImage(PNG)},
    )
    menu_path = created.image_path

    updated = await service.remove_image(STORE_ID, created.id, OWNER_ID, "recipe")

    assert updated.recipe_image_path is None
    assert updated.image_path == menu_path
    assert list(storage.files) == [menu_path]


async def test_remove_image_succeeds_even_if_file_delete_fails(
    service: RecipeService,
    storage: FakeStorage,
) -> None:
    created = await service.create(
        STORE_ID, OWNER_ID, recipe_request(), {"menu": RecipeImage(JPEG)}
    )
    storage.fail_delete = True

    updated = await service.remove_image(STORE_ID, created.id, OWNER_ID, "menu")

    assert updated.image_path is None


async def test_image_urls_signs_all_paths_in_one_call(
    service: RecipeService,
    storage: FakeStorage,
) -> None:
    first = await service.create(
        STORE_ID, OWNER_ID, recipe_request(), {"menu": RecipeImage(JPEG)}
    )
    second = await service.create(
        STORE_ID, OWNER_ID, recipe_request(), {"recipe": RecipeImage(PNG)}
    )
    plain = await service.create(STORE_ID, OWNER_ID, recipe_request())

    urls = await service.image_urls([first, second, plain])

    assert len(storage.signed_with) == 1
    paths, seconds = storage.signed_with[0]
    assert paths == [first.image_path, second.recipe_image_path]
    assert seconds == SIGNED_URL_SECONDS
    assert urls[str(first.image_path)].startswith("https://signed/")


async def test_image_urls_without_images_skips_storage(
    service: RecipeService,
    storage: FakeStorage,
) -> None:
    plain = await service.create(STORE_ID, OWNER_ID, recipe_request())

    assert await service.image_urls([plain]) == {}
    assert storage.signed_with == []


async def test_image_urls_returns_empty_when_storage_fails(
    service: RecipeService,
    storage: FakeStorage,
) -> None:
    created = await service.create(
        STORE_ID, OWNER_ID, recipe_request(), {"menu": RecipeImage(JPEG)}
    )
    storage.fail_sign = True

    assert await service.image_urls([created]) == {}
