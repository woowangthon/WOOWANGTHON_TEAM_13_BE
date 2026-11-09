from collections import defaultdict
from collections.abc import Callable
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol
from uuid import UUID, uuid4
from zoneinfo import ZoneInfo

from app.models.availability import Availability
from app.models.membership import Membership
from app.models.schedule import (
    RecommendationAssignment,
    RecommendationShift,
    Schedule,
    ScheduleAssignment,
    ScheduleRecommendation,
    ScheduleShift,
)
from app.schemas.schedule import (
    RecommendationCreateRequest,
    ScheduleShiftUpdate,
    ScheduleUpdateRequest,
)
from app.services.store_access import StoreAccessProtocol

SEOUL = ZoneInfo("Asia/Seoul")


class RecommendationNotFoundError(Exception):
    """요청한 추천 후보가 존재하지 않습니다."""


class ScheduleNotFoundError(Exception):
    """요청한 확정 스케줄이 존재하지 않습니다."""


class ScheduleAlreadyConfirmedError(Exception):
    """추천 후보가 이미 스케줄로 등록되었습니다."""


class ScheduleInvalidMemberError(Exception):
    """퇴사했거나 다른 매장의 구성원을 배정하려고 했습니다."""


class ScheduleAssignmentConflictError(Exception):
    """한 구성원의 근무 시간이 겹치거나 최소 휴식시간을 위반했습니다."""


class ScheduleStaffOnlyError(Exception):
    """알바생용 내 근무표를 사장님이 요청했습니다."""


class ScheduleRepositoryProtocol(Protocol):
    async def list_availabilities(
        self, store_id: UUID, months: list[date]
    ) -> list[Availability]: ...

    async def create_recommendations(
        self, recommendations: list[ScheduleRecommendation]
    ) -> list[ScheduleRecommendation]: ...

    async def list_recommendations(
        self, store_id: UUID
    ) -> list[ScheduleRecommendation]: ...

    async def get_recommendation(
        self, store_id: UUID, recommendation_id: UUID
    ) -> ScheduleRecommendation | None: ...

    async def get_by_recommendation(
        self, recommendation_id: UUID
    ) -> Schedule | None: ...

    async def create_schedule(self, schedule: Schedule) -> bool: ...

    async def get_schedule(
        self, store_id: UUID, schedule_id: UUID
    ) -> Schedule | None: ...

    async def list_schedules(
        self,
        store_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        published_only: bool = False,
    ) -> list[Schedule]: ...

    async def save_schedule(self, schedule: Schedule) -> Schedule: ...


class MembershipRepositoryProtocol(Protocol):
    async def list_active_by_store_id(self, store_id: UUID) -> list[Membership]: ...

    async def get_active_by_store_and_user_id(
        self, store_id: UUID, user_id: UUID
    ) -> Membership | None: ...


def _parse_time(value: str) -> time:
    hour, minute = (int(part) for part in value.split(":"))
    return time(hour, minute)


def _minutes(start: time, end: time) -> int:
    base = date(2000, 1, 1)
    return int(
        (datetime.combine(base, end) - datetime.combine(base, start)).total_seconds()
        // 60
    )


def _week_start(work_date: date) -> date:
    return work_date - timedelta(days=work_date.weekday())


def _months_between(start_date: date, end_date: date) -> list[date]:
    result: list[date] = []
    cursor = date(start_date.year, start_date.month, 1)
    last = date(end_date.year, end_date.month, 1)
    while cursor <= last:
        result.append(cursor)
        if cursor.month == 12:
            cursor = date(cursor.year + 1, 1, 1)
        else:
            cursor = date(cursor.year, cursor.month + 1, 1)
    return result


def _has_conflict(
    work_date: date,
    start: time,
    end: time,
    assigned: list[tuple[date, time, time]],
    minimum_rest_minutes: int,
) -> bool:
    new_start = datetime.combine(work_date, start)
    new_end = datetime.combine(work_date, end)
    for other_date, other_start, other_end in assigned:
        if other_date != work_date:
            continue
        old_start = datetime.combine(other_date, other_start)
        old_end = datetime.combine(other_date, other_end)
        if new_end <= old_start:
            gap = int((old_start - new_end).total_seconds() // 60)
        elif old_end <= new_start:
            gap = int((new_start - old_end).total_seconds() // 60)
        else:
            return True
        if gap < minimum_rest_minutes:
            return True
    return False


class ScheduleService:
    def __init__(
        self,
        repository: ScheduleRepositoryProtocol,
        memberships: MembershipRepositoryProtocol,
        store_access: StoreAccessProtocol,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._memberships = memberships
        self._store_access = store_access
        self._clock = clock or (lambda: datetime.now(UTC))

    async def _active_members(self, store_id: UUID) -> list[Membership]:
        return await self._memberships.list_active_by_store_id(store_id)

    @staticmethod
    def _availability_statuses(
        availabilities: list[Availability],
    ) -> tuple[set[tuple[UUID, date]], dict[tuple[UUID, date], str]]:
        submitted = {
            (item.membership_id, item.month) for item in availabilities
        }
        statuses = {
            (item.membership_id, day.work_date): day.status
            for item in availabilities
            for day in item.days
        }
        return submitted, statuses

    @staticmethod
    def _candidate_signature(
        recommendation: ScheduleRecommendation,
    ) -> tuple[tuple[str, ...], ...]:
        return tuple(
            tuple(
                sorted(
                    str(assignment.membership_id)
                    for assignment in shift.assignments
                )
            )
            for shift in recommendation.shifts
        )

    def _build_candidate(
        self,
        store_id: UUID,
        batch_id: UUID,
        candidate_no: int,
        request: RecommendationCreateRequest,
        members: list[Membership],
        submitted: set[tuple[UUID, date]],
        statuses: dict[tuple[UUID, date], str],
    ) -> ScheduleRecommendation:
        ordered_members = sorted(members, key=lambda item: (item.joined_at, item.id))
        if ordered_members:
            offset = (candidate_no - 1) % len(ordered_members)
            rotated = ordered_members[offset:] + ordered_members[:offset]
        else:
            rotated = []
        rank = {member.id: index for index, member in enumerate(rotated)}
        weekly_minutes: dict[tuple[UUID, date], int] = defaultdict(int)
        total_minutes: dict[UUID, int] = defaultdict(int)
        assigned: dict[UUID, list[tuple[date, time, time]]] = defaultdict(list)
        shifts: list[RecommendationShift] = []
        unfilled = 0

        for slot in sorted(request.shifts, key=lambda item: (item.date, item.start)):
            start = _parse_time(slot.start)
            end = _parse_time(slot.end)
            duration = _minutes(start, end)
            week = _week_start(slot.date)
            eligible: list[Membership] = []
            for member in ordered_members:
                slot_month = date(slot.date.year, slot.date.month, 1)
                if (member.id, slot_month) not in submitted:
                    continue
                if statuses.get((member.id, slot.date)) != "available":
                    continue
                if (
                    weekly_minutes[(member.id, week)] + duration
                    > request.rules.maximum_weekly_hours * 60
                ):
                    continue
                if _has_conflict(
                    slot.date,
                    start,
                    end,
                    assigned[member.id],
                    request.rules.minimum_rest_minutes,
                ):
                    continue
                eligible.append(member)

            eligible.sort(
                key=lambda member: (
                    statuses.get((member.id, slot.date)) != "available",
                    weekly_minutes[(member.id, week)],
                    total_minutes[member.id],
                    rank[member.id],
                )
            )
            selected = eligible[: slot.required_staff]
            unfilled += slot.required_staff - len(selected)
            for member in selected:
                weekly_minutes[(member.id, week)] += duration
                total_minutes[member.id] += duration
                assigned[member.id].append((slot.date, start, end))

            shifts.append(
                RecommendationShift(
                    work_date=slot.date,
                    start_time=start,
                    end_time=end,
                    role=slot.role,
                    required_staff=slot.required_staff,
                    assignments=[
                        RecommendationAssignment(membership_id=member.id)
                        for member in selected
                    ],
                )
            )

        return ScheduleRecommendation(
            batch_id=batch_id,
            store_id=store_id,
            candidate_no=candidate_no,
            start_date=request.start_date,
            end_date=request.end_date,
            maximum_weekly_hours=request.rules.maximum_weekly_hours,
            minimum_rest_minutes=request.rules.minimum_rest_minutes,
            unfilled_slots=unfilled,
            shifts=shifts,
        )

    async def create_recommendations(
        self,
        store_id: UUID,
        user_id: UUID,
        request: RecommendationCreateRequest,
    ) -> list[ScheduleRecommendation]:
        await self._store_access.ensure_owner(store_id, user_id)
        members = await self._active_members(store_id)
        availabilities = await self._repository.list_availabilities(
            store_id,
            _months_between(request.start_date, request.end_date),
        )
        submitted, statuses = self._availability_statuses(availabilities)
        batch_id = uuid4()
        recommendations: list[ScheduleRecommendation] = []
        signatures: set[tuple[tuple[str, ...], ...]] = set()
        attempts = max(request.recommendation_count, len(members))
        for attempt in range(1, attempts + 1):
            candidate = self._build_candidate(
                store_id,
                batch_id,
                attempt,
                request,
                members,
                submitted,
                statuses,
            )
            signature = self._candidate_signature(candidate)
            if signature in signatures:
                continue
            signatures.add(signature)
            candidate.candidate_no = len(recommendations) + 1
            recommendations.append(candidate)
            if len(recommendations) >= request.recommendation_count:
                break
        if not recommendations:
            recommendations.append(
                self._build_candidate(
                    store_id,
                    batch_id,
                    1,
                    request,
                    members,
                    submitted,
                    statuses,
                )
            )
        return await self._repository.create_recommendations(recommendations)

    async def member_names(self, store_id: UUID) -> dict[UUID, str]:
        members = await self._active_members(store_id)
        return {item.id: item.staff_name for item in members}

    async def list_recommendations(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> list[ScheduleRecommendation]:
        await self._store_access.ensure_owner(store_id, user_id)
        return await self._repository.list_recommendations(store_id)

    async def get_recommendation(
        self,
        store_id: UUID,
        recommendation_id: UUID,
        user_id: UUID,
    ) -> ScheduleRecommendation:
        await self._store_access.ensure_owner(store_id, user_id)
        recommendation = await self._repository.get_recommendation(
            store_id, recommendation_id
        )
        if recommendation is None:
            raise RecommendationNotFoundError
        return recommendation

    async def create_schedule(
        self,
        store_id: UUID,
        recommendation_id: UUID,
        user_id: UUID,
        name: str,
        *,
        publish: bool,
    ) -> Schedule:
        recommendation = await self.get_recommendation(
            store_id, recommendation_id, user_id
        )
        if await self._repository.get_by_recommendation(recommendation_id):
            raise ScheduleAlreadyConfirmedError
        now = self._clock()
        schedule = Schedule(
            store_id=store_id,
            recommendation_id=recommendation.id,
            name=name,
            start_date=recommendation.start_date,
            end_date=recommendation.end_date,
            status="published" if publish else "draft",
            published_at=now if publish else None,
            shifts=[
                ScheduleShift(
                    work_date=shift.work_date,
                    start_time=shift.start_time,
                    end_time=shift.end_time,
                    role=shift.role,
                    assignments=[
                        ScheduleAssignment(membership_id=item.membership_id)
                        for item in shift.assignments
                    ],
                )
                for shift in recommendation.shifts
            ],
        )
        if not await self._repository.create_schedule(schedule):
            raise ScheduleAlreadyConfirmedError
        return schedule

    async def list_schedules(
        self,
        store_id: UUID,
        user_id: UUID,
        start_date: date | None,
        end_date: date | None,
    ) -> list[Schedule]:
        await self._store_access.ensure_owner(store_id, user_id)
        return await self._repository.list_schedules(store_id, start_date, end_date)

    @staticmethod
    def _validate_assignments(
        shifts: list[ScheduleShiftUpdate],
        active_member_ids: set[UUID],
    ) -> None:
        assigned: dict[UUID, list[tuple[date, time, time]]] = defaultdict(list)
        for shift in sorted(shifts, key=lambda item: (item.date, item.start)):
            start = _parse_time(shift.start)
            end = _parse_time(shift.end)
            for member_id in shift.assigned_member_ids:
                if member_id not in active_member_ids:
                    raise ScheduleInvalidMemberError
                if _has_conflict(shift.date, start, end, assigned[member_id], 0):
                    raise ScheduleAssignmentConflictError
                assigned[member_id].append((shift.date, start, end))

    async def update_schedule(
        self,
        store_id: UUID,
        schedule_id: UUID,
        user_id: UUID,
        request: ScheduleUpdateRequest,
    ) -> Schedule:
        await self._store_access.ensure_owner(store_id, user_id)
        schedule = await self._repository.get_schedule(store_id, schedule_id)
        if schedule is None:
            raise ScheduleNotFoundError
        if request.name is not None:
            schedule.name = request.name
        if request.shifts is not None:
            members = await self._active_members(store_id)
            self._validate_assignments(request.shifts, {item.id for item in members})
            schedule.shifts = [
                ScheduleShift(
                    work_date=item.date,
                    start_time=_parse_time(item.start),
                    end_time=_parse_time(item.end),
                    role=item.role,
                    assignments=[
                        ScheduleAssignment(membership_id=member_id)
                        for member_id in item.assigned_member_ids
                    ],
                )
                for item in request.shifts
            ]
            if request.shifts:
                dates = [item.date for item in request.shifts]
                schedule.start_date = min(dates)
                schedule.end_date = max(dates)
        if request.publish is not None:
            schedule.status = "published" if request.publish else "draft"
            schedule.published_at = self._clock() if request.publish else None
        return await self._repository.save_schedule(schedule)

    async def my_schedule(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> tuple[date, date, Membership, list[Schedule], dict[UUID, str]]:
        await self._store_access.ensure_member(store_id, user_id)
        membership = await self._memberships.get_active_by_store_and_user_id(
            store_id, user_id
        )
        if membership is None:
            raise ScheduleStaffOnlyError
        today = self._clock().astimezone(SEOUL).date()
        week_start = _week_start(today)
        schedules = await self._repository.list_schedules(
            store_id,
            week_start,
            None,
            published_only=True,
        )
        members = await self._active_members(store_id)
        return (
            today,
            week_start,
            membership,
            schedules,
            {item.id: item.staff_name for item in members},
        )
