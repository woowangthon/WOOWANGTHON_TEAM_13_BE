from collections.abc import Iterator
from datetime import UTC, date, datetime, time
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.fixed_schedule import (
    FixedShiftAssignment,
    ShiftAssignmentOverride,
    ShiftTemplate,
    SubstituteRequest,
)
from app.models.membership import Membership
from app.models.schedule import (
    Schedule,
    ScheduleAssignment,
    ScheduleRecommendation,
    ScheduleShift,
)
from app.models.store import Store
from app.models.user import User
from app.repositories.payroll import PayrollRepository


class SyncSessionAdapter:
    """실제 쿼리를 SQLite에서 실행하도록 동기 세션을 감쌉니다."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, query: Any) -> Any:
        return self._session.execute(query)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    tables = [
        User.__table__,
        Store.__table__,
        Membership.__table__,
        ScheduleRecommendation.__table__,
        Schedule.__table__,
        ScheduleShift.__table__,
        ScheduleAssignment.__table__,
        ShiftTemplate.__table__,
        FixedShiftAssignment.__table__,
        SubstituteRequest.__table__,
        ShiftAssignmentOverride.__table__,
    ]
    User.metadata.create_all(engine, tables=tables)
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session
    engine.dispose()


def repository(session: Session) -> PayrollRepository:
    return PayrollRepository(cast(AsyncSession, SyncSessionAdapter(session)))


def add_store(session: Session, deleted: bool = False) -> Store:
    store = Store(
        id=uuid4(),
        owner_id=uuid4(),
        name="매장",
        address="주소",
        payday=25,
        deleted_at=datetime.now(UTC) if deleted else None,
    )
    session.add(store)
    return store


def add_member(session: Session, store: Store, left: bool = False) -> Membership:
    membership = Membership(
        id=uuid4(),
        store_id=store.id,
        user_id=uuid4(),
        staff_name="민수",
        hourly_wage=10320,
        tax_type="3.3",
        left_at=datetime.now(UTC) if left else None,
    )
    session.add(membership)
    return membership


def add_shift(
    session: Session,
    store: Store,
    work_date: date,
    members: list[UUID],
    status: str = "published",
) -> None:
    schedule = Schedule(
        id=uuid4(),
        store_id=store.id,
        name="11월",
        start_date=work_date,
        end_date=work_date,
        status=status,
    )
    shift = ScheduleShift(
        id=uuid4(),
        schedule_id=schedule.id,
        work_date=work_date,
        start_time=time(9),
        end_time=time(13),
    )
    session.add_all([schedule, shift])
    session.flush()
    session.add_all(
        [
            ScheduleAssignment(schedule_shift_id=shift.id, membership_id=member)
            for member in members
        ]
    )
    session.flush()


def add_fixed_shift(
    session: Session,
    store: Store,
    member: Membership,
    *,
    weekday: int,
) -> FixedShiftAssignment:
    template = ShiftTemplate(
        id=uuid4(),
        store_id=store.id,
        name="오픈",
        start_time=time(10),
        end_time=time(14),
        role="홀",
        sort_order=0,
    )
    assignment = FixedShiftAssignment(
        id=uuid4(),
        store_id=store.id,
        template_id=template.id,
        weekday=weekday,
        assignee_user_id=member.user_id,
        template=template,
    )
    session.add_all([template, assignment])
    session.flush()
    return assignment


async def test_membership_lookup_returns_store(session: Session) -> None:
    store = add_store(session)
    member = add_member(session, store)
    session.commit()

    found = await repository(session).get_active_membership_with_store(
        store.id, member.user_id
    )

    assert found is not None
    assert found[0].id == member.id
    assert found[1].payday == 25


async def test_membership_lookup_excludes_left_and_deleted(session: Session) -> None:
    store = add_store(session)
    left = add_member(session, store, left=True)
    deleted_store = add_store(session, deleted=True)
    deleted_member = add_member(session, deleted_store)
    session.commit()
    repo = repository(session)

    assert await repo.get_active_membership_with_store(store.id, left.user_id) is None
    assert (
        await repo.get_active_membership_with_store(
            deleted_store.id, deleted_member.user_id
        )
        is None
    )


async def test_shift_times_include_only_my_published_shifts(session: Session) -> None:
    store = add_store(session)
    me = add_member(session, store)
    other = add_member(session, store)
    other_store = add_store(session)
    add_shift(session, store, date(2026, 11, 2), [me.id, other.id])
    add_shift(session, store, date(2026, 11, 3), [other.id])
    add_shift(session, store, date(2026, 11, 4), [me.id], status="draft")
    add_shift(session, store, date(2026, 12, 1), [me.id])
    add_shift(session, other_store, date(2026, 11, 5), [me.id])
    session.commit()

    repo = repository(session)
    mine = await repo.list_published_shift_times(
        store.id, [me.id], date(2026, 10, 26), date(2026, 11, 30)
    )
    both = await repo.list_published_shift_times(
        store.id, [me.id, other.id], date(2026, 10, 26), date(2026, 11, 30)
    )

    assert dict(mine) == {me.id: [(date(2026, 11, 2), time(9), time(13))]}
    assert dict(both) == {
        me.id: [(date(2026, 11, 2), time(9), time(13))],
        other.id: [
            (date(2026, 11, 2), time(9), time(13)),
            (date(2026, 11, 3), time(9), time(13)),
        ],
    }
    assert (
        await repo.list_published_shift_times(
            store.id, [], date(2026, 10, 26), date(2026, 11, 30)
        )
        == {}
    )


async def test_fixed_shift_and_substitute_override_drive_payroll(
    session: Session,
) -> None:
    store = add_store(session)
    original = add_member(session, store)
    substitute = add_member(session, store)
    assignment = add_fixed_shift(session, store, original, weekday=0)
    request = SubstituteRequest(
        id=uuid4(),
        store_id=store.id,
        fixed_assignment_id=assignment.id,
        work_date=date(2026, 11, 9),
        requester_user_id=original.user_id,
        target_user_id=substitute.user_id,
        status="ACCEPTED",
    )
    override = ShiftAssignmentOverride(
        id=uuid4(),
        fixed_assignment_id=assignment.id,
        work_date=date(2026, 11, 9),
        assignee_user_id=substitute.user_id,
        substitute_request_id=request.id,
    )
    session.add_all([request, override])
    session.commit()

    shifts = await repository(session).list_published_shift_times(
        store.id,
        [original.id, substitute.id],
        date(2026, 11, 2),
        date(2026, 11, 16),
    )

    assert shifts[original.id] == [
        (date(2026, 11, 2), time(10), time(14)),
        (date(2026, 11, 16), time(10), time(14)),
    ]
    assert shifts[substitute.id] == [(date(2026, 11, 9), time(10), time(14))]


async def test_membership_lookup_by_id_is_scoped_to_store(session: Session) -> None:
    store = add_store(session)
    member = add_member(session, store)
    left = add_member(session, store, left=True)
    other_store = add_store(session)
    session.commit()
    repo = repository(session)

    found = await repo.get_active_membership_by_id(store.id, member.id)

    assert found is not None and found[0].id == member.id
    assert await repo.get_active_membership_by_id(other_store.id, member.id) is None
    assert await repo.get_active_membership_by_id(store.id, left.id) is None


async def test_list_active_memberships_excludes_left(session: Session) -> None:
    store = add_store(session)
    first = add_member(session, store)
    second = add_member(session, store)
    add_member(session, store, left=True)
    add_member(session, add_store(session))
    deleted_store = add_store(session, deleted=True)
    session.commit()
    repo = repository(session)

    found = await repo.list_active_memberships_with_store(store.id)

    assert found is not None
    assert found[0].id == store.id
    assert {member.id for member in found[1]} == {first.id, second.id}
    assert await repo.list_active_memberships_with_store(deleted_store.id) is None
