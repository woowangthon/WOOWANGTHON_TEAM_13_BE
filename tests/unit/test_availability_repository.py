from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.availability import Availability, AvailabilityDay
from app.models.membership import Membership
from app.models.store import Store
from app.models.user import User
from app.repositories.availability import AvailabilityRepository

NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)
MONTH = date(2026, 12, 1)


class SyncSessionAdapter:
    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, query: Any) -> Any:
        return self._session.execute(query)

    def add(self, item: Any) -> None:
        self._session.add(item)

    async def delete(self, item: Any) -> None:
        self._session.delete(item)

    async def commit(self) -> None:
        self._session.commit()

    async def rollback(self) -> None:
        self._session.rollback()

    async def refresh(self, item: Any) -> None:
        self._session.refresh(item)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    tables = [
        User.__table__,
        Store.__table__,
        Membership.__table__,
        Availability.__table__,
        AvailabilityDay.__table__,
    ]
    User.metadata.create_all(engine, tables=tables)
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session
    engine.dispose()


def as_async(session: Session) -> AsyncSession:
    return cast(AsyncSession, SyncSessionAdapter(session))


def add_member(session: Session, staff_name: str = "지은") -> Membership:
    owner = User(id=uuid4(), auth_user_id=uuid4(), nickname="사장", provider="kakao")
    staff = User(id=uuid4(), auth_user_id=uuid4(), nickname="알바", provider="kakao")
    store = Store(id=uuid4(), owner_id=owner.id, name="카페", address="주소")
    membership = Membership(
        id=uuid4(),
        store_id=store.id,
        user_id=staff.id,
        role="staff",
        staff_name=staff_name,
        hourly_wage=10_320,
        joined_at=NOW,
    )
    session.add_all([owner, staff, store, membership])
    session.commit()
    return membership


def make_availability(
    membership: Membership,
    work_date: date = date(2026, 12, 15),
) -> Availability:
    item = Availability(
        id=uuid4(),
        store_id=membership.store_id,
        membership_id=membership.id,
        month=MONTH,
        memo="시험",
        submitted_at=NOW,
    )
    item.days = [
        AvailabilityDay(
            availability_id=item.id,
            work_date=work_date,
            status="unavailable",
        )
    ]
    return item


async def test_create_and_get_with_days(session: Session) -> None:
    member = add_member(session)
    repository = AvailabilityRepository(as_async(session))
    availability = make_availability(member)

    assert await repository.create(availability)
    found = await repository.get_by_member_and_month(
        member.store_id,
        member.id,
        MONTH,
    )

    assert found is not None
    assert found.id == availability.id
    assert [(item.work_date, item.status) for item in found.days] == [
        (date(2026, 12, 15), "unavailable")
    ]


async def test_unique_member_month_returns_false(session: Session) -> None:
    member = add_member(session)
    repository = AvailabilityRepository(as_async(session))

    assert await repository.create(make_availability(member))
    assert not await repository.create(
        make_availability(member, date(2026, 12, 20))
    )


async def test_get_by_id_is_scoped_to_member_and_store(session: Session) -> None:
    member = add_member(session)
    other = add_member(session, "민지")
    repository = AvailabilityRepository(as_async(session))
    availability = make_availability(member)
    assert await repository.create(availability)

    assert (
        await repository.get_by_id_and_member(
            availability.id,
            member.store_id,
            member.id,
        )
        is not None
    )
    assert (
        await repository.get_by_id_and_member(
            availability.id,
            other.store_id,
            other.id,
        )
        is None
    )


async def test_save_replaces_days_and_delete_cascades(session: Session) -> None:
    member = add_member(session)
    repository = AvailabilityRepository(as_async(session))
    availability = make_availability(member)
    assert await repository.create(availability)
    availability.days = [
        AvailabilityDay(
            availability_id=availability.id,
            work_date=date(2026, 12, 21),
            status="available",
        )
    ]

    await repository.save(availability)
    found = await repository.get_by_member_and_month(
        member.store_id,
        member.id,
        MONTH,
    )
    assert found is not None
    assert [(item.work_date, item.status) for item in found.days] == [
        (date(2026, 12, 21), "available")
    ]

    await repository.delete(found)

    assert session.get(Availability, availability.id) is None
    assert session.query(AvailabilityDay).count() == 0


async def test_list_by_store_and_month_is_isolated(session: Session) -> None:
    first = add_member(session, "지은")
    second = add_member(session, "민지")
    repository = AvailabilityRepository(as_async(session))
    assert await repository.create(make_availability(first))
    assert await repository.create(make_availability(second))

    rows = await repository.list_by_store_and_month(first.store_id, MONTH)

    assert [item.membership_id for item in rows] == [first.id]
