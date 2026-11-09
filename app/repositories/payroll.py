from collections import defaultdict
from collections.abc import Sequence
from datetime import date, time
from uuid import UUID

from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import Membership
from app.models.schedule import Schedule, ScheduleAssignment, ScheduleShift
from app.models.store import Store

PUBLISHED_SCHEDULE = "published"


class PayrollRepository:
    def __init__(self, session: AsyncSession) -> None:
        """급여 계산에 필요한 조회에 사용할 세션을 받습니다."""
        self._session = session

    async def _membership_with_store(
        self,
        store_id: UUID,
        condition: ColumnElement[bool],
    ) -> tuple[Membership, Store] | None:
        """삭제되지 않은 매장의 재직 중인 구성원 한 명과 매장을 조회합니다."""
        query = (
            select(Membership, Store)
            .join(Store, Store.id == Membership.store_id)
            .where(
                Membership.store_id == store_id,
                condition,
                Membership.left_at.is_(None),
                Store.deleted_at.is_(None),
            )
        )
        row = (await self._session.execute(query)).one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    async def get_active_membership_with_store(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> tuple[Membership, Store] | None:
        """사용자의 재직 중인 구성원 정보와 매장을 함께 조회합니다."""
        return await self._membership_with_store(
            store_id,
            Membership.user_id == user_id,
        )

    async def get_active_membership_by_id(
        self,
        store_id: UUID,
        member_id: UUID,
    ) -> tuple[Membership, Store] | None:
        """구성원 ID로 재직 중인 구성원 정보와 매장을 함께 조회합니다."""
        return await self._membership_with_store(
            store_id,
            Membership.id == member_id,
        )

    async def list_active_memberships_with_store(
        self,
        store_id: UUID,
    ) -> tuple[Store, list[Membership]] | None:
        """삭제되지 않은 매장과 재직 중인 구성원을 가입 순서로 조회합니다."""
        store = (
            await self._session.execute(
                select(Store).where(Store.id == store_id, Store.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if store is None:
            return None
        query = (
            select(Membership)
            .where(Membership.store_id == store_id, Membership.left_at.is_(None))
            .order_by(Membership.joined_at, Membership.id)
        )
        memberships = (await self._session.execute(query)).scalars().all()
        return store, list(memberships)

    async def list_published_shift_times(
        self,
        store_id: UUID,
        membership_ids: Sequence[UUID],
        start_date: date,
        end_date: date,
    ) -> dict[UUID, list[tuple[date, time, time]]]:
        """기간 안의 확정 스케줄에서 구성원별로 배정된 근무 시간을 조회합니다."""
        shifts: dict[UUID, list[tuple[date, time, time]]] = defaultdict(list)
        if not membership_ids:
            return shifts
        query = (
            select(
                ScheduleAssignment.membership_id,
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
                ScheduleAssignment.membership_id.in_(membership_ids),
                ScheduleShift.work_date >= start_date,
                ScheduleShift.work_date <= end_date,
            )
            .distinct()
            .order_by(
                ScheduleAssignment.membership_id,
                ScheduleShift.work_date,
                ScheduleShift.start_time,
                ScheduleShift.end_time,
            )
        )
        for member_id, work_date, start, end in (
            await self._session.execute(query)
        ).all():
            shifts[member_id].append((work_date, start, end))
        return shifts
