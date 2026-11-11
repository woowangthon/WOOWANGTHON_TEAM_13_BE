from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from functools import lru_cache
from typing import Literal, Protocol, cast
from uuid import UUID
from zoneinfo import ZoneInfo

import holidays

from app.models.schedule import (
    ScheduleAssignment,
    ScheduleAssignmentOverride,
    ScheduleDayOverride,
    ShiftTemplate,
    SubstituteRequest,
)
from app.repositories.schedule import (
    PendingSubstituteRequestExistsError,
    WorkerRecord,
)
from app.schemas.schedule import (
    DailyScheduleShiftInput,
    ScheduleAssignmentInput,
    ShiftTemplateCreateRequest,
    ShiftTemplateUpdateRequest,
)
from app.services.store_access import StoreAccessProtocol

SEOUL = ZoneInfo("Asia/Seoul")


class ShiftTemplateNotFoundError(Exception):
    pass


class ScheduleAssignmentNotFoundError(Exception):
    pass


class InvalidScheduleWorkerError(Exception):
    pass


class SubstituteRequestNotFoundError(Exception):
    pass


class SubstituteRequestForbiddenError(Exception):
    pass


class SubstituteRequestConflictError(Exception):
    pass


class SubstituteTargetConflictError(Exception):
    pass


class SubstitutePastDateError(Exception):
    pass


class DailyScheduleNotFoundError(Exception):
    pass


class DailyScheduleConflictError(Exception):
    pass


@dataclass(frozen=True)
class ScheduleWorker:
    user_id: UUID
    member_id: UUID | None
    name: str
    role: Literal["owner", "staff"]


@dataclass(frozen=True)
class CalendarOccurrence:
    assignment_id: UUID | None
    daily_shift_id: UUID | None
    template: ShiftTemplate
    start_time: time
    end_time: time
    work_date: date
    assignee_user_id: UUID
    substituted: bool
    manually_adjusted: bool


class ScheduleRepositoryProtocol(Protocol):
    async def list_workers(self, store_id: UUID) -> list[WorkerRecord]: ...
    async def get_store_closure(self, store_id: UUID) -> tuple[list[int], bool]: ...
    async def create_template(self, template: ShiftTemplate) -> ShiftTemplate: ...
    async def list_templates(self, store_id: UUID) -> list[ShiftTemplate]: ...
    async def get_template(
        self, store_id: UUID, template_id: UUID
    ) -> ShiftTemplate | None: ...
    async def save_template(self, template: ShiftTemplate) -> ShiftTemplate: ...
    async def delete_template(self, template: ShiftTemplate) -> None: ...
    async def replace_assignments(
        self, store_id: UUID, assignments: list[ScheduleAssignment]
    ) -> list[ScheduleAssignment]: ...
    async def list_assignments(self, store_id: UUID) -> list[ScheduleAssignment]: ...
    async def get_assignment(
        self, store_id: UUID, assignment_id: UUID
    ) -> ScheduleAssignment | None: ...
    async def list_overrides(
        self, assignment_ids: list[UUID], start_date: date, end_date: date
    ) -> list[ScheduleAssignmentOverride]: ...
    async def get_override(
        self, assignment_id: UUID, work_date: date
    ) -> ScheduleAssignmentOverride | None: ...
    async def list_day_overrides(
        self, store_id: UUID, start_date: date, end_date: date
    ) -> list[ScheduleDayOverride]: ...
    async def get_day_override(
        self, store_id: UUID, work_date: date
    ) -> ScheduleDayOverride | None: ...
    async def replace_day_override(
        self,
        store_id: UUID,
        work_date: date,
        created_by_user_id: UUID,
        shifts: list[tuple[UUID, UUID, time | None, time | None]],
        cancelled_at: datetime,
    ) -> ScheduleDayOverride: ...
    async def delete_day_override(self, override: ScheduleDayOverride) -> None: ...
    async def find_pending_request(
        self, assignment_id: UUID, work_date: date
    ) -> SubstituteRequest | None: ...
    async def create_request(self, request: SubstituteRequest) -> SubstituteRequest: ...
    async def get_request(
        self,
        store_id: UUID,
        request_id: UUID,
        *,
        for_update: bool = False,
    ) -> SubstituteRequest | None: ...
    async def list_requests(
        self,
        store_id: UUID,
        user_id: UUID,
        box: str,
        status: str | None,
    ) -> list[SubstituteRequest]: ...
    async def respond(
        self,
        request: SubstituteRequest,
        responded_at: datetime,
        *,
        accept: bool,
    ) -> SubstituteRequest: ...
    async def mark_received_read(
        self, requests: list[SubstituteRequest], read_at: datetime
    ) -> None: ...


def _parse_time(value: str) -> time:
    hour, minute = (int(part) for part in value.split(":"))
    return time(hour, minute)


def _overlaps(start_a: time, end_a: time, start_b: time, end_b: time) -> bool:
    return start_a < end_b and start_b < end_a


@lru_cache(maxsize=8)
def _korean_holidays(year: int) -> holidays.HolidayBase:
    return holidays.KR(years=year)


def _is_korean_holiday(value: date) -> bool:
    return value in _korean_holidays(value.year)


class ScheduleService:
    def __init__(
        self,
        repository: ScheduleRepositoryProtocol,
        store_access: StoreAccessProtocol,
        clock: Callable[[], datetime] | None = None,
        holiday_checker: Callable[[date], bool] | None = None,
    ) -> None:
        self._repository = repository
        self._store_access = store_access
        self._clock = clock or (lambda: datetime.now(UTC))
        self._holiday_checker = holiday_checker or _is_korean_holiday

    async def workers(self, store_id: UUID, user_id: UUID) -> list[ScheduleWorker]:
        await self._store_access.ensure_member(store_id, user_id)
        return await self._workers(store_id)

    async def _workers(self, store_id: UUID) -> list[ScheduleWorker]:
        records = await self._repository.list_workers(store_id)
        return [
            ScheduleWorker(
                user_id=item[0],
                member_id=item[1],
                name=item[2],
                role=cast(Literal["owner", "staff"], item[3]),
            )
            for item in records
        ]

    async def create_template(
        self,
        store_id: UUID,
        user_id: UUID,
        request: ShiftTemplateCreateRequest,
    ) -> ShiftTemplate:
        await self._store_access.ensure_owner(store_id, user_id)
        return await self._repository.create_template(
            ShiftTemplate(
                store_id=store_id,
                name=request.name,
                start_time=_parse_time(request.start),
                end_time=_parse_time(request.end),
                role=request.role,
                headcount=request.headcount,
                sort_order=request.sort_order,
            )
        )

    async def list_templates(
        self, store_id: UUID, user_id: UUID
    ) -> list[ShiftTemplate]:
        await self._store_access.ensure_member(store_id, user_id)
        return await self._repository.list_templates(store_id)

    async def update_template(
        self,
        store_id: UUID,
        template_id: UUID,
        user_id: UUID,
        request: ShiftTemplateUpdateRequest,
    ) -> ShiftTemplate:
        await self._store_access.ensure_owner(store_id, user_id)
        template = await self._repository.get_template(store_id, template_id)
        if template is None:
            raise ShiftTemplateNotFoundError
        if request.name is not None:
            template.name = request.name
        if request.start is not None:
            template.start_time = _parse_time(request.start)
        if request.end is not None:
            template.end_time = _parse_time(request.end)
        if template.end_time <= template.start_time:
            raise ValueError("end must be later than start")
        if request.role is not None:
            template.role = request.role
        if request.headcount is not None:
            template.headcount = request.headcount
        if request.sort_order is not None:
            template.sort_order = request.sort_order
        return await self._repository.save_template(template)

    async def delete_template(
        self, store_id: UUID, template_id: UUID, user_id: UUID
    ) -> None:
        await self._store_access.ensure_owner(store_id, user_id)
        template = await self._repository.get_template(store_id, template_id)
        if template is None:
            raise ShiftTemplateNotFoundError
        await self._repository.delete_template(template)

    async def replace_schedule(
        self,
        store_id: UUID,
        user_id: UUID,
        inputs: list[ScheduleAssignmentInput],
    ) -> list[ScheduleAssignment]:
        await self._store_access.ensure_owner(store_id, user_id)
        templates = {
            item.id for item in await self._repository.list_templates(store_id)
        }
        workers = {item.user_id for item in await self._workers(store_id)}
        if any(item.template_id not in templates for item in inputs):
            raise ShiftTemplateNotFoundError
        if any(item.assignee_user_id not in workers for item in inputs):
            raise InvalidScheduleWorkerError
        assignments = [
            ScheduleAssignment(
                store_id=store_id,
                template_id=item.template_id,
                weekday=item.weekday,
                assignee_user_id=item.assignee_user_id,
            )
            for item in inputs
        ]
        return await self._repository.replace_assignments(store_id, assignments)

    async def schedule(
        self, store_id: UUID, user_id: UUID
    ) -> tuple[list[ScheduleAssignment], dict[UUID, ScheduleWorker]]:
        await self._store_access.ensure_member(store_id, user_id)
        workers = {item.user_id: item for item in await self._workers(store_id)}
        return await self._repository.list_assignments(store_id), workers

    async def replace_daily_schedule(
        self,
        store_id: UUID,
        user_id: UUID,
        work_date: date,
        inputs: list[DailyScheduleShiftInput],
    ) -> tuple[ScheduleDayOverride, dict[UUID, ScheduleWorker]]:
        await self._store_access.ensure_owner(store_id, user_id)
        templates = {
            item.id: item for item in await self._repository.list_templates(store_id)
        }
        workers = {item.user_id: item for item in await self._workers(store_id)}
        if any(item.template_id not in templates for item in inputs):
            raise ShiftTemplateNotFoundError
        if any(item.assignee_user_id not in workers for item in inputs):
            raise InvalidScheduleWorkerError
        self._validate_daily_conflicts(inputs, templates)
        override = await self._repository.replace_day_override(
            store_id,
            work_date,
            user_id,
            [
                (
                    item.template_id,
                    item.assignee_user_id,
                    _parse_time(item.start) if item.start is not None else None,
                    _parse_time(item.end) if item.end is not None else None,
                )
                for item in inputs
            ],
            self._clock(),
        )
        return override, workers

    async def reset_daily_schedule(
        self,
        store_id: UUID,
        user_id: UUID,
        work_date: date,
    ) -> None:
        await self._store_access.ensure_owner(store_id, user_id)
        override = await self._repository.get_day_override(store_id, work_date)
        if override is None:
            raise DailyScheduleNotFoundError
        await self._repository.delete_day_override(override)

    async def calendar(
        self,
        store_id: UUID,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> tuple[
        list[CalendarOccurrence],
        dict[UUID, ScheduleWorker],
    ]:
        await self._store_access.ensure_member(store_id, user_id)
        if end_date < start_date or (end_date - start_date).days > 62:
            raise ValueError("calendar period must be between 1 and 63 days")
        assignments = await self._repository.list_assignments(store_id)
        closed_weekdays, closed_on_holidays = await self._repository.get_store_closure(
            store_id
        )
        overrides = await self._repository.list_overrides(
            [item.id for item in assignments], start_date, end_date
        )
        override_map = {
            (item.schedule_assignment_id, item.work_date): item.assignee_user_id
            for item in overrides
        }
        day_overrides = {
            item.work_date: item
            for item in await self._repository.list_day_overrides(
                store_id, start_date, end_date
            )
        }
        occurrences: list[CalendarOccurrence] = []
        cursor = start_date
        while cursor <= end_date:
            day_override = day_overrides.get(cursor)
            if day_override is not None:
                occurrences.extend(
                    CalendarOccurrence(
                        assignment_id=None,
                        daily_shift_id=shift.id,
                        template=shift.template,
                        start_time=shift.start_time or shift.template.start_time,
                        end_time=shift.end_time or shift.template.end_time,
                        work_date=cursor,
                        assignee_user_id=shift.assignee_user_id,
                        substituted=False,
                        manually_adjusted=True,
                    )
                    for shift in day_override.shifts
                )
                cursor += timedelta(days=1)
                continue
            if cursor.weekday() in closed_weekdays or (
                closed_on_holidays and self._holiday_checker(cursor)
            ):
                cursor += timedelta(days=1)
                continue
            for assignment in assignments:
                if assignment.weekday != cursor.weekday():
                    continue
                override_user = override_map.get((assignment.id, cursor))
                occurrences.append(
                    CalendarOccurrence(
                        assignment_id=assignment.id,
                        daily_shift_id=None,
                        template=assignment.template,
                        start_time=assignment.template.start_time,
                        end_time=assignment.template.end_time,
                        work_date=cursor,
                        assignee_user_id=(override_user or assignment.assignee_user_id),
                        substituted=override_user is not None,
                        manually_adjusted=False,
                    )
                )
            cursor += timedelta(days=1)
        occurrences.sort(
            key=lambda item: (
                item.work_date,
                item.start_time,
                item.template.sort_order,
                str(item.daily_shift_id or item.assignment_id),
            )
        )
        workers = {item.user_id: item for item in await self._workers(store_id)}
        return occurrences, workers

    async def create_substitute_request(
        self,
        store_id: UUID,
        requester_user_id: UUID,
        assignment_id: UUID,
        work_date: date,
        target_user_id: UUID,
    ) -> tuple[SubstituteRequest, dict[UUID, ScheduleWorker]]:
        await self._store_access.ensure_member(store_id, requester_user_id)
        if await self._repository.get_day_override(store_id, work_date) is not None:
            raise SubstituteRequestConflictError
        assignment = await self._repository.get_assignment(store_id, assignment_id)
        if assignment is None or assignment.weekday != work_date.weekday():
            raise ScheduleAssignmentNotFoundError
        if work_date < self._clock().astimezone(SEOUL).date():
            raise SubstitutePastDateError
        workers = {item.user_id: item for item in await self._workers(store_id)}
        if target_user_id not in workers:
            raise InvalidScheduleWorkerError
        current_user_id = await self._effective_assignee(assignment, work_date)
        if current_user_id != requester_user_id:
            raise SubstituteRequestForbiddenError
        if target_user_id == current_user_id:
            raise SubstituteRequestConflictError
        if await self._repository.find_pending_request(assignment.id, work_date):
            raise SubstituteRequestConflictError
        await self._ensure_no_target_conflict(
            store_id,
            assignment,
            work_date,
            target_user_id,
        )
        try:
            request = await self._repository.create_request(
                SubstituteRequest(
                    store_id=store_id,
                    schedule_assignment_id=assignment.id,
                    work_date=work_date,
                    requester_user_id=requester_user_id,
                    target_user_id=target_user_id,
                )
            )
        except PendingSubstituteRequestExistsError:
            raise SubstituteRequestConflictError from None
        return request, workers

    async def list_substitute_requests(
        self,
        store_id: UUID,
        user_id: UUID,
        box: str,
        status: str | None,
    ) -> tuple[list[SubstituteRequest], dict[UUID, ScheduleWorker]]:
        await self._store_access.ensure_member(store_id, user_id)
        requests = await self._repository.list_requests(store_id, user_id, box, status)
        if box == "received":
            await self._repository.mark_received_read(requests, self._clock())
        workers = {item.user_id: item for item in await self._workers(store_id)}
        return requests, workers

    async def respond_substitute_request(
        self,
        store_id: UUID,
        request_id: UUID,
        user_id: UUID,
        *,
        accept: bool,
    ) -> tuple[SubstituteRequest, dict[UUID, ScheduleWorker]]:
        await self._store_access.ensure_member(store_id, user_id)
        request = await self._repository.get_request(
            store_id, request_id, for_update=True
        )
        if request is None:
            raise SubstituteRequestNotFoundError
        if request.target_user_id != user_id:
            raise SubstituteRequestForbiddenError
        if request.status != "PENDING":
            raise SubstituteRequestConflictError
        if accept:
            assignment = request.assignment
            current_user_id = await self._effective_assignee(
                assignment, request.work_date
            )
            if current_user_id != request.requester_user_id:
                raise SubstituteRequestConflictError
            workers = {item.user_id: item for item in await self._workers(store_id)}
            if user_id not in workers:
                raise InvalidScheduleWorkerError
            await self._ensure_no_target_conflict(
                store_id, assignment, request.work_date, user_id
            )
        request = await self._repository.respond(request, self._clock(), accept=accept)
        workers = {item.user_id: item for item in await self._workers(store_id)}
        return request, workers

    async def _effective_assignee(
        self, assignment: ScheduleAssignment, work_date: date
    ) -> UUID:
        override = await self._repository.get_override(assignment.id, work_date)
        return override.assignee_user_id if override else assignment.assignee_user_id

    @staticmethod
    def _validate_daily_conflicts(
        inputs: list[DailyScheduleShiftInput],
        templates: dict[UUID, ShiftTemplate],
    ) -> None:
        for index, item in enumerate(inputs):
            template = templates[item.template_id]
            start_time = _parse_time(item.start) if item.start else template.start_time
            end_time = _parse_time(item.end) if item.end else template.end_time
            for other in inputs[index + 1 :]:
                if item.assignee_user_id != other.assignee_user_id:
                    continue
                other_template = templates[other.template_id]
                other_start_time = (
                    _parse_time(other.start)
                    if other.start
                    else other_template.start_time
                )
                other_end_time = (
                    _parse_time(other.end) if other.end else other_template.end_time
                )
                if _overlaps(
                    start_time,
                    end_time,
                    other_start_time,
                    other_end_time,
                ):
                    raise DailyScheduleConflictError

    async def _ensure_no_target_conflict(
        self,
        store_id: UUID,
        requested: ScheduleAssignment,
        work_date: date,
        target_user_id: UUID,
    ) -> None:
        assignments = await self._repository.list_assignments(store_id)
        same_day = [item for item in assignments if item.weekday == work_date.weekday()]
        overrides = await self._repository.list_overrides(
            [item.id for item in same_day], work_date, work_date
        )
        override_map = {
            item.schedule_assignment_id: item.assignee_user_id for item in overrides
        }
        for assignment in same_day:
            if assignment.id == requested.id:
                continue
            assignee = override_map.get(assignment.id, assignment.assignee_user_id)
            if assignee != target_user_id:
                continue
            if _overlaps(
                requested.template.start_time,
                requested.template.end_time,
                assignment.template.start_time,
                assignment.template.end_time,
            ):
                raise SubstituteTargetConflictError
