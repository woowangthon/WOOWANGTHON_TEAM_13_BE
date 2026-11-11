from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest

from app.models.schedule import (
    ScheduleAssignment,
    ScheduleAssignmentOverride,
    ScheduleDayOverride,
    ScheduleDayShift,
    ShiftTemplate,
    SubstituteRequest,
)
from app.schemas.schedule import (
    DailyScheduleShiftInput,
    ShiftTemplateCreateRequest,
    ShiftTemplateUpdateRequest,
)
from app.services.schedule import (
    DailyScheduleConflictError,
    ScheduleService,
    SubstituteRequestForbiddenError,
)

STORE_ID = uuid4()
OWNER_ID = uuid4()
STAFF_ID = uuid4()
MEMBER_ID = uuid4()
WORK_DATE = date(2026, 11, 16)
NOW = datetime(2026, 11, 10, 12, tzinfo=UTC)


class StubAccess:
    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        return None

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        return None


class StubRepository:
    def __init__(self) -> None:
        self.template = ShiftTemplate(
            id=uuid4(),
            store_id=STORE_ID,
            name="오픈",
            start_time=time(10),
            end_time=time(14),
            role="홀",
            sort_order=0,
        )
        self.assignment = ScheduleAssignment(
            id=uuid4(),
            store_id=STORE_ID,
            template_id=self.template.id,
            weekday=0,
            assignee_user_id=STAFF_ID,
            template=self.template,
        )
        self.templates = [self.template]
        self.overrides: dict[tuple[UUID, date], ScheduleAssignmentOverride] = {}
        self.requests: dict[UUID, SubstituteRequest] = {}
        self.day_overrides: dict[date, ScheduleDayOverride] = {}
        self.closed_weekdays: list[int] = []
        self.closed_on_holidays = False

    async def get_store_closure(self, store_id: UUID):
        return self.closed_weekdays, self.closed_on_holidays

    async def create_template(self, template: ShiftTemplate):
        template.id = uuid4()
        self.template = template
        self.templates = [template]
        return template

    async def list_templates(self, store_id: UUID):
        return self.templates

    async def get_template(self, store_id: UUID, template_id: UUID):
        return next((item for item in self.templates if item.id == template_id), None)

    async def save_template(self, template: ShiftTemplate):
        self.template = template
        self.templates = [
            template if item.id == template.id else item for item in self.templates
        ]
        return template

    async def list_workers(self, store_id: UUID):
        return [
            (OWNER_ID, None, "박 사장", "owner"),
            (STAFF_ID, MEMBER_ID, "지은", "staff"),
        ]

    async def list_assignments(self, store_id: UUID):
        return [self.assignment]

    async def get_assignment(self, store_id: UUID, assignment_id: UUID):
        return self.assignment if assignment_id == self.assignment.id else None

    async def list_overrides(
        self, assignment_ids: list[UUID], start_date: date, end_date: date
    ):
        return [
            item
            for (_, work_date), item in self.overrides.items()
            if start_date <= work_date <= end_date
        ]

    async def get_override(self, assignment_id: UUID, work_date: date):
        return self.overrides.get((assignment_id, work_date))

    async def list_day_overrides(
        self, store_id: UUID, start_date: date, end_date: date
    ):
        return [
            item
            for work_date, item in self.day_overrides.items()
            if start_date <= work_date <= end_date
        ]

    async def get_day_override(self, store_id: UUID, work_date: date):
        return self.day_overrides.get(work_date)

    async def replace_day_override(
        self,
        store_id: UUID,
        work_date: date,
        created_by_user_id: UUID,
        shifts: list[tuple[UUID, UUID, time | None, time | None]],
        cancelled_at: datetime,
    ):
        templates = {item.id: item for item in self.templates}
        override = ScheduleDayOverride(
            id=uuid4(),
            store_id=store_id,
            work_date=work_date,
            created_by_user_id=created_by_user_id,
            shifts=[
                ScheduleDayShift(
                    id=uuid4(),
                    template_id=template_id,
                    assignee_user_id=assignee_user_id,
                    start_time=start_time,
                    end_time=end_time,
                    template=templates[template_id],
                )
                for template_id, assignee_user_id, start_time, end_time in shifts
            ],
        )
        for request in self.requests.values():
            if request.work_date == work_date and request.status == "PENDING":
                request.status = "CANCELLED"
                request.responded_at = cancelled_at
        self.day_overrides[work_date] = override
        return override

    async def delete_day_override(self, override: ScheduleDayOverride):
        self.day_overrides.pop(override.work_date, None)

    async def find_pending_request(self, assignment_id: UUID, work_date: date):
        return next(
            (
                item
                for item in self.requests.values()
                if item.schedule_assignment_id == assignment_id
                and item.work_date == work_date
                and item.status == "PENDING"
            ),
            None,
        )

    async def create_request(self, request: SubstituteRequest):
        request.id = uuid4()
        request.status = "PENDING"
        request.created_at = NOW
        request.assignment = self.assignment
        self.requests[request.id] = request
        return request

    async def get_request(
        self,
        store_id: UUID,
        request_id: UUID,
        *,
        for_update: bool = False,
    ):
        return self.requests.get(request_id)

    async def respond(
        self,
        request: SubstituteRequest,
        responded_at: datetime,
        *,
        accept: bool,
    ):
        request.status = "ACCEPTED" if accept else "REJECTED"
        request.responded_at = responded_at
        request.target_read_at = responded_at
        if accept:
            self.overrides[(request.schedule_assignment_id, request.work_date)] = (
                ScheduleAssignmentOverride(
                    id=uuid4(),
                    schedule_assignment_id=request.schedule_assignment_id,
                    work_date=request.work_date,
                    assignee_user_id=request.target_user_id,
                    substitute_request_id=request.id,
                )
            )
        return request


@pytest.mark.asyncio
async def test_accepting_substitute_request_changes_only_that_date() -> None:
    repository = StubRepository()
    service = ScheduleService(repository, StubAccess(), clock=lambda: NOW)

    request, _ = await service.create_substitute_request(
        STORE_ID,
        STAFF_ID,
        repository.assignment.id,
        WORK_DATE,
        OWNER_ID,
    )
    accepted, _ = await service.respond_substitute_request(
        STORE_ID,
        request.id,
        OWNER_ID,
        accept=True,
    )
    occurrences, _ = await service.calendar(
        STORE_ID,
        STAFF_ID,
        WORK_DATE,
        WORK_DATE + timedelta(days=7),
    )

    assert accepted.status == "ACCEPTED"
    assert occurrences[0].assignee_user_id == OWNER_ID
    assert occurrences[0].substituted is True
    assert occurrences[1].assignee_user_id == STAFF_ID
    assert occurrences[1].substituted is False


@pytest.mark.asyncio
async def test_only_current_assignee_can_request_substitute() -> None:
    repository = StubRepository()
    service = ScheduleService(repository, StubAccess(), clock=lambda: NOW)

    with pytest.raises(SubstituteRequestForbiddenError):
        await service.create_substitute_request(
            STORE_ID,
            OWNER_ID,
            repository.assignment.id,
            WORK_DATE,
            STAFF_ID,
        )


@pytest.mark.asyncio
async def test_calendar_excludes_closed_weekdays_and_holidays() -> None:
    repository = StubRepository()
    repository.closed_weekdays = [WORK_DATE.weekday()]
    repository.closed_on_holidays = True
    holiday = WORK_DATE + timedelta(days=7)
    service = ScheduleService(
        repository,
        StubAccess(),
        clock=lambda: NOW,
        holiday_checker=lambda value: value == holiday,
    )

    occurrences, _ = await service.calendar(
        STORE_ID,
        STAFF_ID,
        WORK_DATE,
        holiday,
    )

    assert occurrences == []


@pytest.mark.asyncio
async def test_shift_template_headcount_is_created_and_updated() -> None:
    repository = StubRepository()
    service = ScheduleService(repository, StubAccess())

    created = await service.create_template(
        STORE_ID,
        OWNER_ID,
        ShiftTemplateCreateRequest(
            name="오픈",
            start="09:00",
            end="15:00",
            headcount=4,
        ),
    )
    assert created.headcount == 4

    updated = await service.update_template(
        STORE_ID,
        created.id,
        OWNER_ID,
        ShiftTemplateUpdateRequest(headcount=2),
    )

    assert updated.headcount == 2


@pytest.mark.parametrize("headcount", [0, 11])
def test_shift_template_headcount_must_be_between_one_and_ten(
    headcount: int,
) -> None:
    with pytest.raises(ValueError):
        ShiftTemplateCreateRequest(
            name="오픈",
            start="09:00",
            end="15:00",
            headcount=headcount,
        )


@pytest.mark.asyncio
async def test_owner_replaces_only_one_days_schedule_and_can_reset_it() -> None:
    repository = StubRepository()
    service = ScheduleService(repository, StubAccess(), clock=lambda: NOW)

    override, _ = await service.replace_daily_schedule(
        STORE_ID,
        OWNER_ID,
        WORK_DATE,
        [
            DailyScheduleShiftInput(
                template_id=repository.template.id,
                assignee_user_id=OWNER_ID,
            )
        ],
    )
    occurrences, _ = await service.calendar(
        STORE_ID,
        STAFF_ID,
        WORK_DATE,
        WORK_DATE + timedelta(days=7),
    )

    assert override.work_date == WORK_DATE
    assert [(item.work_date, item.assignee_user_id) for item in occurrences] == [
        (WORK_DATE, OWNER_ID),
        (WORK_DATE + timedelta(days=7), STAFF_ID),
    ]
    assert occurrences[0].manually_adjusted is True
    assert occurrences[0].assignment_id is None
    assert occurrences[0].daily_shift_id is not None

    await service.reset_daily_schedule(STORE_ID, OWNER_ID, WORK_DATE)
    restored, _ = await service.calendar(
        STORE_ID,
        STAFF_ID,
        WORK_DATE,
        WORK_DATE,
    )

    assert len(restored) == 1
    assert restored[0].assignee_user_id == STAFF_ID
    assert restored[0].manually_adjusted is False


@pytest.mark.asyncio
async def test_owner_can_delete_every_shift_on_one_date() -> None:
    repository = StubRepository()
    service = ScheduleService(repository, StubAccess(), clock=lambda: NOW)

    await service.replace_daily_schedule(STORE_ID, OWNER_ID, WORK_DATE, [])
    occurrences, _ = await service.calendar(
        STORE_ID,
        STAFF_ID,
        WORK_DATE,
        WORK_DATE + timedelta(days=7),
    )

    assert [item.work_date for item in occurrences] == [WORK_DATE + timedelta(days=7)]


@pytest.mark.asyncio
async def test_owner_can_add_another_shift_on_one_date() -> None:
    repository = StubRepository()
    middle = ShiftTemplate(
        id=uuid4(),
        store_id=STORE_ID,
        name="미들",
        start_time=time(15),
        end_time=time(18),
        role="주방",
        sort_order=1,
    )
    repository.templates.append(middle)
    service = ScheduleService(repository, StubAccess(), clock=lambda: NOW)

    await service.replace_daily_schedule(
        STORE_ID,
        OWNER_ID,
        WORK_DATE,
        [
            DailyScheduleShiftInput(
                template_id=repository.template.id,
                assignee_user_id=STAFF_ID,
            ),
            DailyScheduleShiftInput(
                template_id=middle.id,
                assignee_user_id=OWNER_ID,
            ),
        ],
    )
    occurrences, _ = await service.calendar(
        STORE_ID,
        STAFF_ID,
        WORK_DATE,
        WORK_DATE,
    )

    assert [(item.template.name, item.assignee_user_id) for item in occurrences] == [
        ("오픈", STAFF_ID),
        ("미들", OWNER_ID),
    ]


@pytest.mark.asyncio
async def test_owner_can_change_time_for_only_one_date() -> None:
    repository = StubRepository()
    service = ScheduleService(repository, StubAccess(), clock=lambda: NOW)

    override, _ = await service.replace_daily_schedule(
        STORE_ID,
        OWNER_ID,
        WORK_DATE,
        [
            DailyScheduleShiftInput(
                template_id=repository.template.id,
                assignee_user_id=STAFF_ID,
                start="11:30",
                end="16:30",
            )
        ],
    )
    occurrences, _ = await service.calendar(
        STORE_ID,
        STAFF_ID,
        WORK_DATE,
        WORK_DATE + timedelta(days=7),
    )

    assert override.shifts[0].start_time == time(11, 30)
    assert override.shifts[0].end_time == time(16, 30)
    assert (occurrences[0].start_time, occurrences[0].end_time) == (
        time(11, 30),
        time(16, 30),
    )
    assert (occurrences[1].start_time, occurrences[1].end_time) == (
        time(10),
        time(14),
    )


@pytest.mark.parametrize(
    "payload",
    [
        {"start": "11:00"},
        {"end": "16:00"},
        {"start": "16:00", "end": "11:00"},
        {"start": "9:00", "end": "11:00"},
    ],
)
def test_daily_schedule_custom_time_requires_valid_range(
    payload: dict[str, str],
) -> None:
    with pytest.raises(ValueError):
        DailyScheduleShiftInput(
            template_id=uuid4(),
            assignee_user_id=uuid4(),
            **payload,
        )


@pytest.mark.asyncio
async def test_daily_schedule_rejects_overlapping_shifts_for_same_worker() -> None:
    repository = StubRepository()
    overlapping = ShiftTemplate(
        id=uuid4(),
        store_id=STORE_ID,
        name="미들",
        start_time=time(12),
        end_time=time(16),
        role="홀",
        sort_order=1,
    )

    repository.templates.append(overlapping)
    service = ScheduleService(repository, StubAccess(), clock=lambda: NOW)

    with pytest.raises(DailyScheduleConflictError):
        await service.replace_daily_schedule(
            STORE_ID,
            OWNER_ID,
            WORK_DATE,
            [
                DailyScheduleShiftInput(
                    template_id=repository.template.id,
                    assignee_user_id=STAFF_ID,
                ),
                DailyScheduleShiftInput(
                    template_id=overlapping.id,
                    assignee_user_id=STAFF_ID,
                ),
            ],
        )
