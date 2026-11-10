from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest

from app.models.schedule import (
    ScheduleAssignment,
    ScheduleAssignmentOverride,
    ShiftTemplate,
    SubstituteRequest,
)
from app.services.schedule import (
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
        self.overrides: dict[tuple[UUID, date], ScheduleAssignmentOverride] = {}
        self.requests: dict[UUID, SubstituteRequest] = {}

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
    assert occurrences[0][2:] == (OWNER_ID, True)
    assert occurrences[1][2:] == (STAFF_ID, False)


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
