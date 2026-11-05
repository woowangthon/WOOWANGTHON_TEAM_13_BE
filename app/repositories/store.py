from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.store import Store


class StoreRepository:
    def __init__(self, session: AsyncSession) -> None:
        """매장 데이터 접근에 사용할 DB 세션을 받습니다."""
        self._session = session

    async def create(self, store: Store) -> Store:
        """새 매장을 저장합니다."""
        self._session.add(store)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(store)
        return store

    async def list_by_owner_id(self, owner_id: UUID) -> list[Store]:
        """소유자가 관리하는 활성 매장 목록을 조회합니다."""
        query = (
            select(Store)
            .where(
                Store.owner_id == owner_id,
                Store.deleted_at.is_(None),
            )
            .order_by(Store.created_at, Store.id)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_by_id_and_owner_id(
        self,
        store_id: UUID,
        owner_id: UUID,
    ) -> Store | None:
        """소유자에게 속한 활성 매장을 조회합니다."""
        query = select(Store).where(
            Store.id == store_id,
            Store.owner_id == owner_id,
            Store.deleted_at.is_(None),
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def save(self, store: Store) -> Store:
        """변경된 매장 정보를 저장합니다."""
        self._session.add(store)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(store)
        return store
