from datetime import date
from uuid import UUID

from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.notification import ScheduleChangeNotice
from app.services.schedule_change import ScheduleChange


class ScheduleChangeRepository:
    def __init__(self, session: AsyncSession) -> None:
        """근무 변경 알림 기록에 사용할 DB 세션을 받습니다."""
        self._session = session

    async def record(
        self,
        store_id: UUID,
        work_date: date,
        changes: list[ScheduleChange],
    ) -> None:
        """근무가 달라진 직원마다 알림 기록을 한 번에 저장합니다."""
        if not changes:
            return
        self._session.add_all(
            ScheduleChangeNotice(
                store_id=store_id,
                user_id=change.user_id,
                work_date=work_date,
                change=change.change,
                shifts_text=change.shifts_text,
            )
            for change in changes
        )
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
