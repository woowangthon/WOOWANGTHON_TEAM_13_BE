"""실제 저장소를 통한 날짜 경계·이력·예상 급여 회귀 테스트."""

from datetime import UTC, date, datetime, time, timedelta
from types import SimpleNamespace
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.db.base import Base
from app.models.invitation import Invitation, InvitationScheduleAssignment
from app.models.membership import Membership
from app.models.schedule import (
    ScheduleAssignment,
    ScheduleAssignmentOverride,
    ScheduleDayOverride,
    ScheduleDayShift,
    ShiftTemplate,
    SubstituteRequest,
)
from app.models.store import Store
from app.models.user import User
from app.repositories.invitation import InvitationRepository
from app.repositories.payroll import PayrollRepository
from app.repositories.schedule import ScheduleRepository
from app.schemas.schedule import (
    DailyScheduleShiftInput,
    ScheduleAssignmentInput,
    ShiftTemplateUpdateRequest,
)
from app.services.payroll_estimate import PayrollEstimateService
from app.services.schedule import (
    InvalidScheduleWorkerError,
    ScheduleAssignmentNotFoundError,
    ScheduleService,
)
from app.services.schedule_history import local_date

# Sunday 23:30 KST. Tomorrow is Monday, so tests catch UTC/KST boundary errors.
NOW = datetime(2026, 11, 15, 14, 30, tzinfo=UTC)
TODAY = date(2026, 11, 15)
TOMORROW = TODAY + timedelta(days=1)


class SessionAdapter:
    def __init__(self, session: Session) -> None:
        self.session = session

    async def execute(self, statement: Any) -> Any:
        return self.session.execute(statement)

    def add(self, value: Any) -> None:
        self.session.add(value)

    def add_all(self, values: list[Any]) -> None:
        self.session.add_all(values)

    async def flush(self) -> None:
        self.session.flush()

    async def commit(self) -> None:
        self.session.commit()

    async def rollback(self) -> None:
        self.session.rollback()

    async def refresh(self, value: Any) -> None:
        self.session.refresh(value)

    async def delete(self, value: Any) -> None:
        self.session.delete(value)


class Access:
    async def ensure_owner(self, *args: Any) -> None:
        pass

    async def ensure_member(self, *args: Any) -> None:
        pass


@pytest.fixture
def world():
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine, expire_on_commit=False) as session:
        owner = User(
            id=uuid4(), auth_user_id=uuid4(), nickname="사장", provider="kakao"
        )
        staff = User(
            id=uuid4(), auth_user_id=uuid4(), nickname="직원", provider="kakao"
        )
        store = Store(
            id=uuid4(),
            owner_id=owner.id,
            name="매장",
            address="주소",
            created_at=NOW - timedelta(days=60),
        )
        member = Membership(
            id=uuid4(),
            store_id=store.id,
            user_id=staff.id,
            staff_name="직원",
            hourly_wage=12000,
            tax_type="none",
            joined_at=NOW - timedelta(days=30),
        )
        template = ShiftTemplate(
            id=uuid4(),
            store_id=store.id,
            name="오픈",
            start_time=time(9),
            end_time=time(13),
            role="홀",
            headcount=1,
            sort_order=0,
        )
        assignments = [
            ScheduleAssignment(
                id=uuid4(),
                store_id=store.id,
                template_id=template.id,
                template=template,
                weekday=weekday,
                assignee_user_id=staff.id,
                effective_from=local_date(member.joined_at),
            )
            for weekday in range(7)
        ]
        session.add_all([owner, staff, store, member, template, *assignments])
        session.commit()
        adapter = cast(AsyncSession, SessionAdapter(session))
        repository = ScheduleRepository(adapter)
        payroll = PayrollRepository(adapter)
        service = ScheduleService(repository, Access(), clock=lambda: NOW)
        yield SimpleNamespace(
            session=session,
            adapter=adapter,
            owner=owner,
            staff=staff,
            store=store,
            member=member,
            template=template,
            assignments=assignments,
            repository=repository,
            payroll=payroll,
            service=service,
        )
    engine.dispose()


async def shifts(world, start=TODAY, end=TOMORROW):
    occurrences, _ = await world.service.calendar(
        world.store.id,
        world.owner.id,
        start,
        end,
    )
    payroll = await world.payroll.list_user_shift_times(
        world.store.id,
        world.staff.id,
        start,
        end,
    )
    assert payroll == [
        (item.work_date, item.start_time, item.end_time)
        for item in occurrences
        if item.assignee_user_id == world.staff.id
    ]
    return occurrences


async def test_replacing_schedule_preserves_today_and_prior_days(world):
    inputs = [
        ScheduleAssignmentInput(
            template_id=world.template.id,
            weekday=0,
            assignee_user_id=world.owner.id,
        )
    ]
    await world.service.replace_schedule(world.store.id, world.owner.id, inputs)
    result = await shifts(world, TODAY - timedelta(days=1))
    assert [item.assignee_user_id for item in result] == [
        world.staff.id,
        world.staff.id,
        world.owner.id,
    ]
    assert all(item.effective_until == TOMORROW for item in world.assignments)
    current, _ = await world.service.schedule(world.store.id, world.owner.id)
    assert len(current) == 1
    assert current[0].effective_from == TOMORROW
    with pytest.raises(ScheduleAssignmentNotFoundError):
        await world.service.create_substitute_request(
            world.store.id,
            world.staff.id,
            world.assignments[0].id,
            TOMORROW,
            world.owner.id,
        )


async def test_repeated_edits_same_day_keep_history_and_latest_next_day(world):
    await world.service.replace_schedule(world.store.id, world.owner.id, [])
    inputs = [
        ScheduleAssignmentInput(
            template_id=world.template.id,
            weekday=day,
            assignee_user_id=world.staff.id,
        )
        for day in range(7)
    ]
    await world.service.replace_schedule(world.store.id, world.owner.id, inputs)
    current, _ = await world.service.schedule(world.store.id, world.owner.id)
    ids = [item.id for item in current]
    # An unchanged PUT preserves IDs and any accepted substitute overrides.
    await world.service.replace_schedule(world.store.id, world.owner.id, inputs)
    current, _ = await world.service.schedule(world.store.id, world.owner.id)
    assert [item.id for item in current] == ids
    assert len(await shifts(world)) == 2
    await world.service.replace_schedule(world.store.id, world.owner.id, [])
    result = await shifts(world)
    assert [item.work_date for item in result] == [TODAY]


async def test_template_updates_preserve_history_and_same_day_snapshot(world):
    for hour in [10, 11]:
        await world.service.update_template(
            world.store.id,
            world.template.id,
            world.owner.id,
            ShiftTemplateUpdateRequest(name="미들", start=f"{hour}:00", end="17:00"),
        )
    result = await shifts(world)
    assert [
        (item.template.name, item.start_time, item.end_time) for item in result
    ] == [
        ("오픈", time(9), time(13)),
        ("미들", time(11), time(17)),
    ]
    assert len(world.template.history) == 1
    later = ScheduleService(
        world.repository, Access(), clock=lambda: NOW + timedelta(days=1)
    )
    await later.update_template(
        world.store.id,
        world.template.id,
        world.owner.id,
        ShiftTemplateUpdateRequest(start="12:00", end="18:00"),
    )
    result = await shifts(world, TODAY, TOMORROW + timedelta(days=1))
    assert [item.start_time for item in result] == [time(9), time(11), time(12)]
    assert len(world.template.history) == 2


async def test_template_changes_respect_midnight_in_seoul(world):
    # UTC Sunday but already Monday in Seoul: application starts on Tuesday.
    service = ScheduleService(
        world.repository,
        Access(),
        clock=lambda: datetime(2026, 11, 15, 15, 1, tzinfo=UTC),
    )
    await service.update_template(
        world.store.id,
        world.template.id,
        world.owner.id,
        ShiftTemplateUpdateRequest(start="10:00"),
    )
    result = await shifts(world, TODAY, TOMORROW + timedelta(days=1))
    assert [item.start_time for item in result] == [time(9), time(9), time(10)]


async def test_template_deletion_preserves_past_and_allows_name_reuse(world):
    await world.service.delete_template(
        world.store.id, world.template.id, world.owner.id
    )
    assert [item.work_date for item in await shifts(world)] == [TODAY]
    assert await world.repository.list_templates(world.store.id) == []
    replacement = ShiftTemplate(
        store_id=world.store.id,
        name="오픈",
        start_time=time(10),
        end_time=time(14),
    )
    await world.repository.create_template(replacement)
    assert replacement.id != world.template.id
    assert world.session.get(ShiftTemplate, world.template.id) is not None


async def test_daily_overrides_use_history_and_explicit_times(world):
    # Legacy daily overrides have nullable times; those follow the date's version.
    world.session.add_all(
        [
            ScheduleDayOverride(
                store_id=world.store.id,
                work_date=TODAY,
                created_by_user_id=world.owner.id,
                shifts=[
                    ScheduleDayShift(
                        template_id=world.template.id, assignee_user_id=world.staff.id
                    )
                ],
            ),
            ScheduleDayOverride(
                store_id=world.store.id,
                work_date=TOMORROW,
                created_by_user_id=world.owner.id,
                shifts=[
                    ScheduleDayShift(
                        template_id=world.template.id,
                        assignee_user_id=world.staff.id,
                        start_time=time(7),
                        end_time=time(8),
                    )
                ],
            ),
        ]
    )
    world.session.commit()
    await world.service.update_template(
        world.store.id,
        world.template.id,
        world.owner.id,
        ShiftTemplateUpdateRequest(start="10:00", end="17:00"),
    )
    result = await shifts(world)
    assert [item.start_time for item in result] == [time(9), time(7)]


async def test_daily_edit_defaults_to_historical_template_and_rejects_prejoin(world):
    await world.service.update_template(
        world.store.id,
        world.template.id,
        world.owner.id,
        ShiftTemplateUpdateRequest(start="10:00", end="17:00"),
    )
    inputs = [
        DailyScheduleShiftInput(
            template_id=world.template.id,
            assignee_user_id=world.staff.id,
        )
    ]
    override, _ = await world.service.replace_daily_schedule(
        world.store.id,
        world.owner.id,
        TODAY,
        inputs,
    )
    assert override.shifts[0].start_time == time(9)
    with pytest.raises(InvalidScheduleWorkerError):
        await world.service.replace_daily_schedule(
            world.store.id,
            world.owner.id,
            local_date(world.member.joined_at) - timedelta(days=1),
            inputs,
        )


async def test_removed_future_request_is_cancelled_and_past_override_retained(world):
    today_assignment = world.assignments[TODAY.weekday()]
    future_assignment = world.assignments[TOMORROW.weekday()]
    past = SubstituteRequest(
        id=uuid4(),
        store_id=world.store.id,
        schedule_assignment_id=today_assignment.id,
        work_date=TODAY,
        requester_user_id=world.staff.id,
        target_user_id=world.owner.id,
        status="ACCEPTED",
    )
    pending = SubstituteRequest(
        id=uuid4(),
        store_id=world.store.id,
        schedule_assignment_id=future_assignment.id,
        work_date=TOMORROW,
        requester_user_id=world.staff.id,
        target_user_id=world.owner.id,
        status="PENDING",
    )
    world.session.add_all(
        [
            past,
            pending,
            ScheduleAssignmentOverride(
                schedule_assignment_id=today_assignment.id,
                work_date=TODAY,
                assignee_user_id=world.owner.id,
                substitute_request_id=past.id,
            ),
        ]
    )
    world.session.commit()
    await world.service.replace_schedule(world.store.id, world.owner.id, [])
    assert pending.status == "CANCELLED"
    assert past.status == "ACCEPTED"
    result = await shifts(world)
    assert len(result) == 1
    assert result[0].assignee_user_id == world.owner.id
    assert result[0].substituted


async def test_invitation_schedule_starts_on_actual_join_day(world):
    invitation = Invitation(
        id=uuid4(),
        store_id=world.store.id,
        created_by_user_id=world.owner.id,
        code="ABC234",
        staff_name="신입",
        hourly_wage=12000,
        created_at=NOW - timedelta(days=5),
        schedule=[
            InvitationScheduleAssignment(template_id=world.template.id, weekday=day)
            for day in range(7)
        ],
    )
    new_user = User(id=uuid4(), auth_user_id=uuid4(), nickname="신입", provider="kakao")
    world.session.add_all([invitation, new_user])
    world.session.commit()
    member = Membership(
        id=uuid4(),
        store_id=world.store.id,
        user_id=new_user.id,
        staff_name="신입",
        hourly_wage=12000,
        tax_type="none",
        joined_at=datetime(2026, 11, 15, 15, 1, tzinfo=UTC),
    )
    await InvitationRepository(world.adapter).accept(invitation, member)
    result, _ = await world.service.calendar(
        world.store.id, world.owner.id, TODAY, TOMORROW
    )
    assert [
        item.work_date for item in result if item.assignee_user_id == new_user.id
    ] == [TOMORROW]
    payroll = await world.payroll.list_published_shift_times(
        world.store.id,
        [member.id],
        TODAY,
        TOMORROW,
    )
    assert payroll[member.id] == [(TOMORROW, time(9), time(13))]


async def test_future_month_payroll_expands_fixed_schedule(world):
    await world.service.replace_schedule(
        world.store.id,
        world.owner.id,
        [
            ScheduleAssignmentInput(
                template_id=world.template.id,
                weekday=0,
                assignee_user_id=world.staff.id,
            ),
        ],
    )
    service = PayrollEstimateService(world.payroll, Access(), clock=lambda: NOW)
    estimates = await service.list_estimates(world.store.id, world.owner.id, "2027-06")
    estimate = estimates.estimates[0]
    assert [item.work_date for item in estimate.work_days] == [
        date(2027, 6, day) for day in [7, 14, 21, 28]
    ]
    assert all(item.status == "planned" for item in estimate.work_days)
    assert estimate.result.base_pay == 4 * 4 * 12000


async def test_invalid_template_range_does_not_mutate_history(world):
    with pytest.raises(ValueError):
        await world.service.update_template(
            world.store.id,
            world.template.id,
            world.owner.id,
            ShiftTemplateUpdateRequest(start="15:00"),
        )
    assert world.template.start_time == time(9)
    assert world.template.history == []
    assert len(await shifts(world)) == 2


async def test_rejoin_closes_pending_future_assignments_without_losing_past(world):
    await world.service.replace_schedule(world.store.id, world.owner.id, [])
    await world.service.replace_schedule(
        world.store.id,
        world.owner.id,
        [
            ScheduleAssignmentInput(
                template_id=world.template.id,
                weekday=0,
                assignee_user_id=world.staff.id,
            ),
        ],
    )
    invitation = Invitation(
        id=uuid4(),
        store_id=world.store.id,
        created_by_user_id=world.owner.id,
        code="XYZ234",
        staff_name="재입장",
        hourly_wage=12000,
        schedule=[
            InvitationScheduleAssignment(template_id=world.template.id, weekday=0)
        ],
    )
    world.session.add(invitation)
    world.session.commit()
    world.member.joined_at = NOW
    await InvitationRepository(world.adapter).accept(invitation, world.member)
    # A future assignment ending at its own start is empty, not an invalid range.
    assert [
        item.work_date
        for item in await shifts(world, TODAY - timedelta(days=1), TOMORROW)
    ] == [TODAY - timedelta(days=1), TOMORROW]


@pytest.mark.parametrize("join_offset, expected_days", [(0, [TODAY]), (1, [])])
async def test_invitation_respects_template_deletion_date(
    world, join_offset, expected_days
):
    invitation = Invitation(
        id=uuid4(),
        store_id=world.store.id,
        created_by_user_id=world.owner.id,
        code="XYZ234",
        staff_name="입장",
        hourly_wage=12000,
        schedule=[
            InvitationScheduleAssignment(template_id=world.template.id, weekday=day)
            for day in range(7)
        ],
    )
    world.session.add(invitation)
    world.session.commit()
    await world.service.delete_template(
        world.store.id, world.template.id, world.owner.id
    )
    newcomer = User(id=uuid4(), auth_user_id=uuid4(), nickname="신입", provider="kakao")
    world.session.add(newcomer)
    world.session.commit()
    member = Membership(
        store_id=world.store.id,
        user_id=newcomer.id,
        staff_name="신입",
        hourly_wage=12000,
        joined_at=NOW + timedelta(days=join_offset),
    )
    await InvitationRepository(world.adapter).accept(invitation, member)
    assert [
        item.work_date
        for item in await shifts(world)
        if item.assignee_user_id == newcomer.id
    ] == expected_days
