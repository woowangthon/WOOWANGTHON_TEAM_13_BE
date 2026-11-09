from collections.abc import Sequence
from datetime import UTC, date, datetime, time
from decimal import Decimal
from uuid import UUID, uuid4

import pytest

from app.models.membership import Membership
from app.models.store import Store
from app.services.payroll_estimate import (
    PayrollEstimateNotFoundError,
    PayrollEstimateService,
    PayrollStaffOnlyError,
    ShiftTime,
    shift_hours,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError

STORE_ID = uuid4()
OWNER_ID = uuid4()
STAFF_ID = uuid4()
OTHER_STAFF_ID = uuid4()
# 2026-11-01(일) 17:00 KST
NOW = datetime(2026, 11, 1, 8, tzinfo=UTC)
SHIFTS: list[ShiftTime] = [
    (date(2026, 10, 30), time(9), time(17)),
    (date(2026, 11, 1), time(9), time(17)),
    (date(2026, 11, 30), time(10), time(14, 30)),
]


def make_membership(user_id: UUID, name: str, tax_type: str = "none") -> Membership:
    return Membership(
        id=uuid4(),
        store_id=STORE_ID,
        user_id=user_id,
        staff_name=name,
        hourly_wage=10000,
        tax_type=tax_type,
    )


class FakeRepository:
    def __init__(self, tax_type: str = "none") -> None:
        self.membership = make_membership(STAFF_ID, "민수", tax_type)
        self.other = make_membership(OTHER_STAFF_ID, "지은")
        self.store = Store(id=STORE_ID, owner_id=OWNER_ID, payday=10)
        self.range: tuple[date, date] | None = None
        self.requested: list[UUID] = []

    @property
    def members(self) -> list[Membership]:
        return [self.membership, self.other]

    async def get_active_membership_with_store(
        self, store_id: UUID, user_id: UUID
    ) -> tuple[Membership, Store] | None:
        for member in self.members:
            if store_id == STORE_ID and member.user_id == user_id:
                return member, self.store
        return None

    async def get_active_membership_by_id(
        self, store_id: UUID, member_id: UUID
    ) -> tuple[Membership, Store] | None:
        for member in self.members:
            if store_id == STORE_ID and member.id == member_id:
                return member, self.store
        return None

    async def list_active_memberships_with_store(
        self, store_id: UUID
    ) -> tuple[Store, list[Membership]] | None:
        if store_id != STORE_ID:
            return None
        return self.store, self.members

    async def list_published_shift_times(
        self,
        store_id: UUID,
        membership_ids: Sequence[UUID],
        start_date: date,
        end_date: date,
    ) -> dict[UUID, list[ShiftTime]]:
        self.range = (start_date, end_date)
        self.requested = list(membership_ids)
        shifts = [s for s in SHIFTS if start_date <= s[0] <= end_date]
        return {self.membership.id: shifts}


class FakeStoreAccess:
    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        if user_id == OWNER_ID:
            return
        if user_id in (STAFF_ID, OTHER_STAFF_ID):
            raise StoreAccessForbiddenError
        raise StoreNotFoundError

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        if user_id not in (OWNER_ID, STAFF_ID, OTHER_STAFF_ID):
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
    assert repository.requested == [repository.membership.id]
    assert estimate.member_id == repository.membership.id
    assert estimate.staff_name == "민수"
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


async def test_owner_lists_every_active_member_in_one_query() -> None:
    repository = FakeRepository()

    estimates = await make_service(repository).list_estimates(
        STORE_ID, OWNER_ID, "2026-11"
    )

    assert repository.requested == [repository.membership.id, repository.other.id]
    assert estimates.month == "2026-11"
    assert estimates.payday == 10
    assert [e.staff_name for e in estimates.estimates] == ["민수", "지은"]
    assert estimates.estimates[0].result.gross_pay == 157000
    # 근무가 없는 직원도 0원으로 포함
    assert estimates.estimates[1].result.gross_pay == 0


@pytest.mark.parametrize(
    ("user_id", "error"),
    [(STAFF_ID, StoreAccessForbiddenError), (uuid4(), StoreNotFoundError)],
)
async def test_only_owner_can_list(user_id: UUID, error: type[Exception]) -> None:
    with pytest.raises(error):
        await make_service(FakeRepository()).list_estimates(STORE_ID, user_id, None)


async def test_owner_reads_any_member_detail() -> None:
    repository = FakeRepository()

    estimate = await make_service(repository).get_estimate(
        STORE_ID, OWNER_ID, repository.membership.id, "2026-11"
    )

    assert estimate.member_id == repository.membership.id
    assert estimate.result.gross_pay == 157000


async def test_staff_reads_own_detail() -> None:
    repository = FakeRepository()

    estimate = await make_service(repository).get_estimate(
        STORE_ID, STAFF_ID, repository.membership.id, "2026-11"
    )

    assert estimate.staff_name == "민수"


async def test_staff_cannot_read_other_member_detail() -> None:
    repository = FakeRepository()

    with pytest.raises(StoreAccessForbiddenError):
        await make_service(repository).get_estimate(
            STORE_ID, STAFF_ID, repository.other.id, None
        )


async def test_unknown_member_detail_is_not_found_for_owner() -> None:
    with pytest.raises(PayrollEstimateNotFoundError):
        await make_service(FakeRepository()).get_estimate(
            STORE_ID, OWNER_ID, uuid4(), None
        )


def test_shift_hours_counts_minutes() -> None:
    assert shift_hours(time(9, 20), time(12)) == Decimal(160) / Decimal(60)
