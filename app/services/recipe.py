from collections import Counter
from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from app.models.recipe import Recipe
from app.schemas.recipe import RecipeCreateRequest, RecipeUpdateRequest
from app.services.store_access import StoreAccessProtocol


class RecipeNotFoundError(Exception):
    """매장에서 레시피를 찾지 못했을 때 발생합니다."""


class RecipeRepositoryProtocol(Protocol):
    async def create(self, recipe: Recipe) -> Recipe: ...

    async def list_by_store_id(self, store_id: UUID) -> list[Recipe]: ...

    async def get_by_id_and_store_id(
        self,
        recipe_id: UUID,
        store_id: UUID,
    ) -> Recipe | None: ...

    async def save(self, recipe: Recipe) -> Recipe: ...


def count_categories(recipes: list[Recipe]) -> dict[str, int]:
    """레시피가 처음 등장한 순서대로 카테고리별 개수를 셉니다."""
    return dict(Counter(recipe.category for recipe in recipes))


class RecipeService:
    def __init__(
        self,
        repository: RecipeRepositoryProtocol,
        store_access: StoreAccessProtocol,
    ) -> None:
        """레시피 비즈니스 로직에 사용할 저장소와 권한 검사기를 받습니다."""
        self._repository = repository
        self._store_access = store_access

    async def _get_recipe(self, store_id: UUID, recipe_id: UUID) -> Recipe:
        """매장의 레시피를 조회하고 없으면 예외를 발생시킵니다."""
        recipe = await self._repository.get_by_id_and_store_id(recipe_id, store_id)
        if recipe is None:
            raise RecipeNotFoundError
        return recipe

    async def create(
        self,
        store_id: UUID,
        user_id: UUID,
        request: RecipeCreateRequest,
    ) -> Recipe:
        """매장의 레시피를 등록합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        recipe = Recipe(
            store_id=store_id,
            **request.model_dump(by_alias=False),
        )
        return await self._repository.create(recipe)

    async def list_for_store(self, store_id: UUID, user_id: UUID) -> list[Recipe]:
        """매장의 레시피 목록을 조회합니다."""
        await self._store_access.ensure_member(store_id, user_id)
        return await self._repository.list_by_store_id(store_id)

    async def get(self, store_id: UUID, recipe_id: UUID, user_id: UUID) -> Recipe:
        """매장의 레시피 상세 정보를 조회합니다."""
        await self._store_access.ensure_member(store_id, user_id)
        return await self._get_recipe(store_id, recipe_id)

    async def update(
        self,
        store_id: UUID,
        recipe_id: UUID,
        user_id: UUID,
        request: RecipeUpdateRequest,
    ) -> Recipe:
        """매장의 레시피를 수정합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        recipe = await self._get_recipe(store_id, recipe_id)
        fields: Mapping[str, Any] = request.model_dump(
            exclude_unset=True,
            by_alias=False,
        )
        for field, value in fields.items():
            setattr(recipe, field, value)
        return await self._repository.save(recipe)

    async def delete(self, store_id: UUID, recipe_id: UUID, user_id: UUID) -> None:
        """매장의 레시피를 삭제 처리합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        recipe = await self._get_recipe(store_id, recipe_id)
        recipe.deleted_at = datetime.now(UTC)
        await self._repository.save(recipe)
