from uuid import UUID, uuid4

import pytest

from app.models.recipe import Recipe
from app.schemas.recipe import RecipeCreateRequest, RecipeUpdateRequest
from app.services.recipe import RecipeNotFoundError, RecipeService, count_categories
from app.services.store import StoreNotFoundError


class FakeRecipeRepository:
    def __init__(self) -> None:
        self.recipes: list[Recipe] = []

    async def create(self, recipe: Recipe) -> Recipe:
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


STORE_ID = uuid4()
OWNER_ID = uuid4()


@pytest.fixture
def repository() -> FakeRecipeRepository:
    return FakeRecipeRepository()


@pytest.fixture
def service(repository: FakeRecipeRepository) -> RecipeService:
    return RecipeService(repository, FakeStoreAccess())


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
