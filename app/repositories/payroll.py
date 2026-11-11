from collections import defaultdict
from collections.abc import Sequence
from datetime import date, time, timedelta
from uuid import UUID

import holidays
from sqlalchemy import ColumnElement, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.membership import Membership
from app.models.schedule import (
    ScheduleAssignment,
    ScheduleAssignmentOverride,
    ScheduleDayOverride,
    ScheduleDayShift,
)
from app.models.store import Store


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
        """고정 스케줄, 대타, 날짜별 조정, 매장 휴무를 합쳐 구성원별로 조회합니다."""
        shifts: dict[UUID, list[tuple[date, time, time]]] = defaultdict(list)
        if not membership_ids:
            return shifts
        member_rows = (
            await self._session.execute(
                select(Membership.id, Membership.user_id).where(
                    Membership.id.in_(membership_ids),
                    Membership.store_id == store_id,
                )
            )
        ).all()
        member_by_user = {user_id: member_id for member_id, user_id in member_rows}
        by_user = await self._shift_times_by_user(store_id, start_date, end_date)
        for user_id, member_id in member_by_user.items():
            if user_id in by_user:
                shifts[member_id] = by_user[user_id]
        return shifts

    async def list_user_shift_times(
        self,
        store_id: UUID,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[tuple[date, time, time]]:
        """사장님을 포함한 사용자 한 명의 기간 안 근무를 조회합니다."""
        by_user = await self._shift_times_by_user(store_id, start_date, end_date)
        return by_user.get(user_id, [])

    async def _store_closure(self, store_id: UUID) -> tuple[set[int], bool]:
        """매장의 쉬는 요일과 공휴일 휴무 여부를 조회합니다."""
        row = (
            await self._session.execute(
                select(Store.closed_weekdays, Store.closed_on_holidays).where(
                    Store.id == store_id
                )
            )
        ).one_or_none()
        if row is None:
            return set(), False
        return set(row[0] or []), bool(row[1])

    async def _shift_times_by_user(
        self,
        store_id: UUID,
        start_date: date,
        end_date: date,
    ) -> dict[UUID, list[tuple[date, time, time]]]:
        """달력과 같은 규칙으로 사용자별 근무를 계산합니다."""
        shifts: dict[UUID, list[tuple[date, time, time]]] = defaultdict(list)
        schedule_assignments = list(
            (
                await self._session.execute(
                    select(ScheduleAssignment)
                    .options(selectinload(ScheduleAssignment.template))
                    .where(ScheduleAssignment.store_id == store_id)
                )
            )
            .scalars()
            .all()
        )
        day_overrides = list(
            (
                await self._session.execute(
                    select(ScheduleDayOverride)
                    .options(
                        selectinload(ScheduleDayOverride.shifts).selectinload(
                            ScheduleDayShift.template
                        )
                    )
                    .where(
                        ScheduleDayOverride.store_id == store_id,
                        ScheduleDayOverride.work_date.between(start_date, end_date),
                    )
                )
            )
            .scalars()
            .all()
        )
        if not schedule_assignments and not day_overrides:
            return shifts
        overrides = (
            await self._session.execute(
                select(ScheduleAssignmentOverride).where(
                    ScheduleAssignmentOverride.schedule_assignment_id.in_(
                        [item.id for item in schedule_assignments]
                    ),
                    ScheduleAssignmentOverride.work_date.between(start_date, end_date),
                )
            )
        ).scalars()
        override_map = {
            (item.schedule_assignment_id, item.work_date): item.assignee_user_id
            for item in overrides
        }
        day_override_map = {item.work_date: item for item in day_overrides}
        closed_weekdays, closed_on_holidays = await self._store_closure(store_id)
        korean_holidays = (
            holidays.KR(years=range(start_date.year, end_date.year + 1))
            if closed_on_holidays
            else {}
        )
        cursor = start_date
        while cursor <= end_date:
            day_override = day_override_map.get(cursor)
            if day_override is not None:
                for shift in day_override.shifts:
                    shifts[shift.assignee_user_id].append(
                        (
                            cursor,
                            shift.start_time or shift.template.start_time,
                            shift.end_time or shift.template.end_time,
                        )
                    )
            elif cursor.weekday() not in closed_weekdays and (
                cursor not in korean_holidays
            ):
                for assignment in schedule_assignments:
                    if assignment.weekday != cursor.weekday():
                        continue
                    user_id = override_map.get(
                        (assignment.id, cursor), assignment.assignee_user_id
                    )
                    shifts[user_id].append(
                        (
                            cursor,
                            assignment.template.start_time,
                            assignment.template.end_time,
                        )
                    )
            cursor += timedelta(days=1)
        for user_shifts in shifts.values():
            user_shifts.sort(key=lambda item: (item[0], item[1], item[2]))
        return shifts
