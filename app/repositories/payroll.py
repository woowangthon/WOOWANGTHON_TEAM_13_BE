from datetime import date, time
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import Membership
from app.models.schedule import Schedule, ScheduleAssignment, ScheduleShift
from app.models.store import Store

PUBLISHED_SCHEDULE = "published"


class PayrollRepository:
    def __init__(self, session: AsyncSession) -> None:
        """급여 계산에 필요한 조회에 사용할 세션을 받습니다."""
        self._session = session

    async def get_active_membership_with_store(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> tuple[Membership, Store] | None:
        """삭제되지 않은 매장의 재직 중인 구성원과 매장을 함께 조회합니다."""
        query = (
            select(Membership, Store)
            .join(Store, Store.id == Membership.store_id)
            .where(
                Membership.store_id == store_id,
                Membership.user_id == user_id,
                Membership.left_at.is_(None),
                Store.deleted_at.is_(None),
            )
        )
        row = (await self._session.execute(query)).one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    async def list_published_shift_times(
        self,
        store_id: UUID,
        membership_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[tuple[date, time, time]]:
        """기간 안의 확정 스케줄에서 구성원에게 배정된 근무 시간을 조회합니다."""
        query = (
            select(
                ScheduleShift.work_date,
                ScheduleShift.start_time,
                ScheduleShift.end_time,
            )
            .join(Schedule, Schedule.id == ScheduleShift.schedule_id)
            .join(
                ScheduleAssignment,
                ScheduleAssignment.schedule_shift_id == ScheduleShift.id,
            )
            .where(
                Schedule.store_id == store_id,
                Schedule.status == PUBLISHED_SCHEDULE,
                ScheduleAssignment.membership_id == membership_id,
                ScheduleShift.work_date >= start_date,
                ScheduleShift.work_date <= end_date,
            )
            .distinct()
            .order_by(ScheduleShift.work_date, ScheduleShift.start_time)
        )
        result = await self._session.execute(query)
        return [(row[0], row[1], row[2]) for row in result.all()]
