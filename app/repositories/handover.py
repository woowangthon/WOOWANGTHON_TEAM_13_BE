from datetime import date
from uuid import UUID

from sqlalchemy import Select, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.handover import HandoverItem, HandoverNote


def _note_query() -> Select[HandoverNote]:
    """작성자와 항목을 함께 읽는 노트 쿼리를 만듭니다."""
    return (
        select(HandoverNote)
        .options(
            selectinload(HandoverNote.author),
            selectinload(HandoverNote.items).selectinload(HandoverItem.checked_by),
        )
        .execution_options(populate_existing=True)
    )


class HandoverRepository:
    def __init__(self, session: AsyncSession) -> None:
        """인수인계 데이터 접근에 사용할 DB 세션을 받습니다."""
        self._session = session

    async def list_by_date(
        self,
        store_id: UUID,
        work_date: date,
    ) -> list[HandoverNote]:
        """매장의 날짜별 노트를 최신 순으로 조회합니다."""
        query = (
            _note_query()
            .where(
                HandoverNote.store_id == store_id,
                HandoverNote.work_date == work_date,
                HandoverNote.deleted_at.is_(None),
            )
            .order_by(HandoverNote.created_at.desc(), HandoverNote.id)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_by_id_and_store_id(
        self,
        note_id: UUID,
        store_id: UUID,
    ) -> HandoverNote | None:
        """매장에 속한 활성 노트를 조회합니다."""
        query = _note_query().where(
            HandoverNote.id == note_id,
            HandoverNote.store_id == store_id,
            HandoverNote.deleted_at.is_(None),
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def save(self, note: HandoverNote) -> HandoverNote:
        """노트와 항목을 저장하고 연관 정보까지 다시 읽습니다."""
        self._session.add(note)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        result = await self._session.execute(
            _note_query().where(HandoverNote.id == note.id)
        )
        return result.scalar_one()
