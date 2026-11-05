from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.recipe import Recipe


class RecipeRepository:
    def __init__(self, session: AsyncSession) -> None:
        """레시피 데이터 접근에 사용할 DB 세션을 받습니다."""
        self._session = session

    async def create(self, recipe: Recipe) -> Recipe:
        """새 레시피를 저장합니다."""
        return await self.save(recipe)

    async def list_by_store_id(self, store_id: UUID) -> list[Recipe]:
        """매장의 활성 레시피를 등록 순으로 조회합니다."""
        query = (
            select(Recipe)
            .where(
                Recipe.store_id == store_id,
                Recipe.deleted_at.is_(None),
            )
            .order_by(Recipe.created_at, Recipe.id)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_by_id_and_store_id(
        self,
        recipe_id: UUID,
        store_id: UUID,
    ) -> Recipe | None:
        """매장에 속한 활성 레시피를 조회합니다."""
        query = select(Recipe).where(
            Recipe.id == recipe_id,
            Recipe.store_id == store_id,
            Recipe.deleted_at.is_(None),
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def save(self, recipe: Recipe) -> Recipe:
        """변경된 레시피를 저장합니다."""
        self._session.add(recipe)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(recipe)
        return recipe
