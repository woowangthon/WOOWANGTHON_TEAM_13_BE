from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.manual import Manual, ManualCategory


class ManualRepository:
    def __init__(self, session: AsyncSession) -> None:
        """매뉴얼 데이터 접근에 사용할 DB 세션을 받습니다."""
        self._session = session

    async def _commit(self, entity: Manual | ManualCategory) -> None:
        """변경 내용을 저장하고 최신 값을 다시 읽습니다."""
        self._session.add(entity)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(entity)

    async def create_category(self, category: ManualCategory) -> ManualCategory:
        """새 매뉴얼 카테고리를 저장합니다."""
        await self._commit(category)
        return category

    async def get_category(
        self,
        category_id: UUID,
        store_id: UUID,
    ) -> ManualCategory | None:
        """매장에 속한 카테고리를 조회합니다."""
        query = select(ManualCategory).where(
            ManualCategory.id == category_id,
            ManualCategory.store_id == store_id,
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_category_by_name(
        self,
        store_id: UUID,
        name: str,
    ) -> ManualCategory | None:
        """매장에서 이름이 같은 카테고리 중 가장 먼저 만든 것을 조회합니다."""
        query = (
            select(ManualCategory)
            .where(
                ManualCategory.store_id == store_id,
                ManualCategory.name == name,
            )
            .order_by(ManualCategory.created_at, ManualCategory.id)
            .limit(1)
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, manual: Manual) -> Manual:
        """새 매뉴얼을 저장합니다."""
        await self._commit(manual)
        return manual

    async def list_by_store_id(self, store_id: UUID) -> list[Manual]:
        """매장의 활성 매뉴얼을 최신 수정 순으로 조회합니다."""
        query = (
            select(Manual)
            .where(
                Manual.store_id == store_id,
                Manual.deleted_at.is_(None),
            )
            .order_by(Manual.updated_at.desc(), Manual.id)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_by_id_and_store_id(
        self,
        manual_id: UUID,
        store_id: UUID,
    ) -> Manual | None:
        """매장에 속한 활성 매뉴얼을 조회합니다."""
        query = select(Manual).where(
            Manual.id == manual_id,
            Manual.store_id == store_id,
            Manual.deleted_at.is_(None),
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def save(self, manual: Manual) -> Manual:
        """변경된 매뉴얼을 저장합니다."""
        await self._commit(manual)
        return manual
