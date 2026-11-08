from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.models.availability import Availability
from app.models.membership import Membership
from app.schemas.availability import AvailabilityDayInput
from app.services.availability import (
    AvailabilityClosedError,
    AvailabilityExistsError,
    AvailabilityInvalidDaysError,
    AvailabilityNotFoundError,
    AvailabilityService,
    AvailabilityStaffOnlyError,
    active_period,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError

STORE_ID = uuid4()
OWNER_ID = uuid4()
STAFF_ID = uuid4()
OUTSIDER_ID = uuid4()
MEMBER_ID = uuid4()
NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)


class FakeAccess:
    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        if store_id != STORE_ID or user_id == OUTSIDER_ID:
            raise StoreNotFoundError

    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        if store_id != STORE_ID:
            raise StoreNotFoundError
        if user_id == STAFF_ID:
            raise StoreAccessForbiddenError
        if user_id != OWNER_ID:
            raise StoreNotFoundError


class FakeMemberships:
    def __init__(self) -> None:
        self.membership = Membership(
            id=MEMBER_ID,
            store_id=STORE_ID,
            user_id=STAFF_ID,
            role="staff",
            staff_name="지은",
            hourly_wage=10_320,
            joined_at=NOW,
        )

    async def get_active_by_store_and_user_id(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> Membership | None:
        if (store_id, user_id) == (STORE_ID, STAFF_ID):
            return self.membership
        return None

    async def list_active_by_store_id(self, store_id: UUID) -> list[Membership]:
        return [self.membership] if store_id == STORE_ID else []


class FakeAvailabilities:
    def __init__(self) -> None:
        self.items: list[Availability] = []
        self.race_on_create = False

    async def get_by_member_and_month(
        self,
        store_id: UUID,
        membership_id: UUID,
        month: date,
    ) -> Availability | None:
        return next(
            (
                item
                for item in self.items
                if (item.store_id, item.membership_id, item.month)
                == (store_id, membership_id, month)
            ),
            None,
        )

    async def get_by_id_and_member(
        self,
        availability_id: UUID,
        store_id: UUID,
        membership_id: UUID,
    ) -> Availability | None:
        return next(
            (
                item
                for item in self.items
                if (item.id, item.store_id, item.membership_id)
                == (availability_id, store_id, membership_id)
            ),
            None,
        )

    async def list_by_store_and_month(
        self,
        store_id: UUID,
        month: date,
    ) -> list[Availability]:
        return [
            item
            for item in self.items
            if item.store_id == store_id and item.month == month
        ]

    async def create(self, availability: Availability) -> bool:
        if self.race_on_create:
            return False
        availability.id = uuid4()
        self.items.append(availability)
        return True

    async def save(self, availability: Availability) -> Availability:
        return availability

    async def delete(self, availability: Availability) -> None:
        self.items.remove(availability)


class Harness:
    def __init__(self, now: datetime = NOW) -> None:
        self.now = now
        self.repository = FakeAvailabilities()
        self.memberships = FakeMemberships()
        self.service = AvailabilityService(
            self.repository,
            self.memberships,
            FakeAccess(),
            lambda: self.now,
        )

    async def create(self) -> Availability:
        view = await self.service.create(
            STORE_ID,
            STAFF_ID,
            "2026-12",
            [AvailabilityDayInput(date=date(2026, 12, 15), status="unavailable")],
            "기말고사",
        )
        assert view.availability is not None
        return view.availability


def test_active_period_moves_after_the_25th() -> None:
    before = active_period(date(2026, 11, 25))
    after = active_period(date(2026, 11, 26))

    assert before.month == date(2026, 12, 1)
    assert before.deadline == date(2026, 11, 25)
    assert after.month == date(2027, 1, 1)
    assert after.deadline == date(2026, 12, 25)


async def test_get_mine_returns_open_period_without_submission() -> None:
    view = await Harness().service.get_mine(STORE_ID, STAFF_ID)

    assert view.period.month == date(2026, 12, 1)
    assert view.period.deadline == date(2026, 11, 25)
    assert view.availability is None


async def test_create_saves_month_days_and_memo() -> None:
    availability = await Harness().create()

    assert availability.membership_id == MEMBER_ID
    assert availability.month == date(2026, 12, 1)
    assert availability.memo == "기말고사"
    assert [(item.work_date, item.status) for item in availability.days] == [
        (date(2026, 12, 15), "unavailable")
    ]


async def test_create_rejects_duplicate_and_concurrent_duplicate() -> None:
    harness = Harness()
    await harness.create()

    with pytest.raises(AvailabilityExistsError):
        await harness.create()

    other = Harness()
    other.repository.race_on_create = True
    with pytest.raises(AvailabilityExistsError):
        await other.create()


async def test_create_rejects_closed_month() -> None:
    harness = Harness(datetime(2026, 11, 26, 12, tzinfo=UTC))

    with pytest.raises(AvailabilityClosedError):
        await harness.create()


async def test_owner_cannot_submit_and_outsider_cannot_see_store() -> None:
    harness = Harness()

    with pytest.raises(AvailabilityStaffOnlyError):
        await harness.service.get_mine(STORE_ID, OWNER_ID)
    with pytest.raises(StoreNotFoundError):
        await harness.service.get_mine(STORE_ID, OUTSIDER_ID)


async def test_update_replaces_days_and_submission_time() -> None:
    harness = Harness()
    availability = await harness.create()
    harness.now = datetime(2026, 11, 21, 12, tzinfo=UTC)

    view = await harness.service.update(
        STORE_ID,
        availability.id,
        STAFF_ID,
        [AvailabilityDayInput(date=date(2026, 12, 20), status="available")],
        "수정",
    )

    assert view.availability is availability
    assert availability.memo == "수정"
    assert availability.submitted_at == harness.now
    assert [(item.work_date, item.status) for item in availability.days] == [
        (date(2026, 12, 20), "available")
    ]


async def test_update_rejects_other_month_day_and_unknown_id() -> None:
    harness = Harness()
    availability = await harness.create()

    with pytest.raises(AvailabilityInvalidDaysError):
        await harness.service.update(
            STORE_ID,
            availability.id,
            STAFF_ID,
            [AvailabilityDayInput(date=date(2027, 1, 1), status="available")],
            "",
        )
    with pytest.raises(AvailabilityNotFoundError):
        await harness.service.update(STORE_ID, uuid4(), STAFF_ID, [], "")


async def test_delete_removes_own_submission() -> None:
    harness = Harness()
    availability = await harness.create()

    await harness.service.delete(STORE_ID, availability.id, STAFF_ID)

    assert harness.repository.items == []


async def test_owner_lists_submissions_and_availabilities() -> None:
    harness = Harness()
    availability = await harness.create()

    period, submitted = await harness.service.list_store_availabilities(
        STORE_ID,
        OWNER_ID,
        "2026-12",
    )
    _, statuses = await harness.service.list_submissions(
        STORE_ID,
        OWNER_ID,
        "2026-12",
    )

    assert period.month == date(2026, 12, 1)
    assert submitted[0].membership.staff_name == "지은"
    assert submitted[0].availability is availability
    assert statuses[0].availability is availability


async def test_staff_cannot_use_owner_lists() -> None:
    harness = Harness()

    with pytest.raises(StoreAccessForbiddenError):
        await harness.service.list_submissions(STORE_ID, STAFF_ID, None)
