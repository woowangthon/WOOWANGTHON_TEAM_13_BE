from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.models.membership import Membership
from app.models.store import Store
from app.services.payroll_estimate import (
    PayrollEstimateService,
    PayrollStaffOnlyError,
    shift_hours,
)
from app.services.store import StoreNotFoundError

STORE_ID = uuid4()
OWNER_ID = uuid4()
STAFF_ID = uuid4()
# 2026-11-01(일) 17:00 KST
NOW = datetime(2026, 11, 1, 8, tzinfo=UTC)
SHIFTS = [
    (date(2026, 10, 30), time(9), time(17)),
    (date(2026, 11, 1), time(9), time(17)),
    (date(2026, 11, 30), time(10), time(14, 30)),
]


class FakeRepository:
    def __init__(self, tax_type: str = "none") -> None:
        self.membership = Membership(
            id=uuid4(),
            store_id=STORE_ID,
            user_id=STAFF_ID,
            staff_name="민수",
            hourly_wage=10000,
            tax_type=tax_type,
        )
        self.store = Store(id=STORE_ID, owner_id=OWNER_ID, payday=10)
        self.range: tuple[date, date] | None = None

    async def get_active_membership_with_store(
        self, store_id: UUID, user_id: UUID
    ) -> tuple[Membership, Store] | None:
        if store_id == STORE_ID and user_id == STAFF_ID:
            return self.membership, self.store
        return None

    async def list_published_shift_times(
        self,
        store_id: UUID,
        membership_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[tuple[date, time, time]]:
        assert membership_id == self.membership.id
        self.range = (start_date, end_date)
        return [shift for shift in SHIFTS if start_date <= shift[0] <= end_date]


class FakeStoreAccess:
    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        if user_id != OWNER_ID:
            raise StoreNotFoundError

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        if user_id not in (OWNER_ID, STAFF_ID):
            raise StoreNotFoundError


def make_service(
    repository: FakeRepository, now: datetime = NOW
) -> PayrollEstimateService:
    return PayrollEstimateService(repository, FakeStoreAccess(), lambda: now)


async def test_estimate_uses_schedule_and_cross_month_week() -> None:
    repository = FakeRepository()

    estimate = await make_service(repository).estimate_mine(
        STORE_ID, STAFF_ID, "2026-11"
    )

    assert repository.range == (date(2026, 10, 26), date(2026, 12, 6))
    assert estimate.month == "2026-11"
    assert estimate.payday == 10
    assert estimate.tax_type == "none"
    assert estimate.result.hours == Decimal("12.5")
    assert estimate.result.base_pay == 125000
    # 10/26 주(일요일 11/1)는 10/30 근무까지 16시간이라 주휴수당 대상
    assert [week.week_start for week in estimate.result.weeks] == [date(2026, 10, 26)]
    assert estimate.result.weekly_allowance == 32000
    assert estimate.result.gross_pay == 157000
    assert estimate.result.net_pay == 157000


async def test_work_days_are_limited_to_month_with_status() -> None:
    estimate = await make_service(FakeRepository()).estimate_mine(
        STORE_ID, STAFF_ID, "2026-11"
    )

    assert [(day.work_date, day.status) for day in estimate.work_days] == [
        (date(2026, 11, 1), "worked"),
        (date(2026, 11, 30), "planned"),
    ]
    assert estimate.work_days[1].hours == Decimal("4.5")


async def test_missing_month_uses_korean_current_month() -> None:
    # UTC로는 10/31이지만 한국 시간은 11/1
    now = datetime(2026, 10, 31, 16, tzinfo=UTC)

    estimate = await make_service(FakeRepository(), now).estimate_mine(
        STORE_ID, STAFF_ID, None
    )

    assert estimate.month == "2026-11"


async def test_deduction_follows_membership_tax_type() -> None:
    estimate = await make_service(FakeRepository("ins")).estimate_mine(
        STORE_ID, STAFF_ID, "2026-11"
    )

    assert estimate.tax_type == "ins"
    # 157000 × 9.7174% = 15256.3 → 15260
    assert estimate.result.deduction == 15260
    assert estimate.result.net_pay == 141740


async def test_month_without_shifts_is_zero() -> None:
    estimate = await make_service(FakeRepository()).estimate_mine(
        STORE_ID, STAFF_ID, "2026-08"
    )

    assert estimate.work_days == []
    assert estimate.result.gross_pay == 0
    assert estimate.result.weeks == []


async def test_owner_without_membership_is_rejected() -> None:
    with pytest.raises(PayrollStaffOnlyError):
        await make_service(FakeRepository()).estimate_mine(STORE_ID, OWNER_ID, None)


async def test_outsider_gets_store_not_found() -> None:
    with pytest.raises(StoreNotFoundError):
        await make_service(FakeRepository()).estimate_mine(STORE_ID, uuid4(), None)


def test_shift_hours_counts_minutes() -> None:
    assert shift_hours(time(9, 20), time(12)) == Decimal(160) / Decimal(60)
