from calendar import monthrange
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from decimal import Decimal
from typing import Literal, Protocol, cast
from uuid import UUID
from zoneinfo import ZoneInfo

from app.models.membership import Membership
from app.models.store import Store
from app.services.payroll import (
    PayrollResult,
    PayrollWorkDay,
    TaxType,
    calculate_payroll,
)
from app.services.store_access import StoreAccessProtocol

SEOUL = ZoneInfo("Asia/Seoul")
WorkStatus = Literal["worked", "planned"]
ShiftTime = tuple[date, time, time]
# 월을 걸친 주의 주휴수당을 계산하려고 앞뒤 6일을 함께 조회합니다.
WEEK_MARGIN = timedelta(days=6)


class PayrollStaffOnlyError(Exception):
    """구성원이 아닌 사장님이 내 예상 급여를 요청했을 때 발생합니다."""


class PayrollEstimateNotFoundError(Exception):
    """매장에서 재직 중인 구성원의 예상 급여를 찾지 못했을 때 발생합니다."""


class PayrollRepositoryProtocol(Protocol):
    async def get_active_membership_with_store(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> tuple[Membership, Store] | None: ...

    async def get_active_membership_by_id(
        self,
        store_id: UUID,
        member_id: UUID,
    ) -> tuple[Membership, Store] | None: ...

    async def list_active_memberships_with_store(
        self,
        store_id: UUID,
    ) -> tuple[Store, list[Membership]] | None: ...

    async def list_published_shift_times(
        self,
        store_id: UUID,
        membership_ids: Sequence[UUID],
        start_date: date,
        end_date: date,
    ) -> dict[UUID, list[ShiftTime]]: ...


@dataclass(frozen=True, slots=True)
class EstimateWorkDay:
    """예상 급여에 포함된 근무 한 건입니다."""

    work_date: date
    start: time
    end: time
    hours: Decimal
    status: WorkStatus


@dataclass(frozen=True, slots=True)
class PayrollEstimate:
    """구성원 한 명의 한 달 예상 급여입니다."""

    store_id: UUID
    member_id: UUID
    staff_name: str
    month: str
    hourly_wage: int
    payday: int | None
    tax_type: TaxType
    weekly_allowance_enabled: bool
    work_days: list[EstimateWorkDay]
    result: PayrollResult


@dataclass(frozen=True, slots=True)
class PayrollEstimateList:
    """사장님이 보는 매장 직원별 예상 급여 목록입니다."""

    store_id: UUID
    month: str
    payday: int | None
    estimates: list[PayrollEstimate]


@dataclass(frozen=True, slots=True)
class MonthPeriod:
    """계산할 달의 첫날과 마지막 날입니다."""

    year: int
    month: int
    first_day: date
    last_day: date

    @property
    def label(self) -> str:
        """YYYY-MM 형식의 월 문자열입니다."""
        return f"{self.year:04d}-{self.month:02d}"


def parse_month(month: str | None, now: datetime) -> MonthPeriod:
    """YYYY-MM 문자열을 계산 기간으로 바꾸고, 없으면 한국 시간 기준 이번 달을 씁니다."""
    if month is None:
        local = now.astimezone(SEOUL)
        year, month_number = local.year, local.month
    else:
        year_text, month_text = month.split("-")
        year, month_number = int(year_text), int(month_text)
    last = monthrange(year, month_number)[1]
    return MonthPeriod(
        year,
        month_number,
        date(year, month_number, 1),
        date(year, month_number, last),
    )


def shift_hours(start: time, end: time) -> Decimal:
    """근무 시작·종료 시각으로 근무시간을 계산합니다."""
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    return Decimal(minutes) / Decimal(60)


def work_status(work_date: date, end: time, now: datetime) -> WorkStatus:
    """근무 종료 시각이 지났으면 worked, 아니면 planned를 반환합니다."""
    ended_at = datetime.combine(work_date, end, tzinfo=SEOUL)
    return "worked" if ended_at <= now else "planned"


def build_estimate(
    membership: Membership,
    store: Store,
    period: MonthPeriod,
    shifts: list[ShiftTime],
    now: datetime,
) -> PayrollEstimate:
    """구성원 정보와 확정 근무로 한 달 예상 급여를 계산합니다."""
    tax_type = cast(TaxType, membership.tax_type)
    result = calculate_payroll(
        year=period.year,
        month=period.month,
        hourly_wage=membership.hourly_wage,
        tax_type=tax_type,
        weekly_allowance_enabled=True,
        work_days=[
            PayrollWorkDay(work_date, shift_hours(start, end))
            for work_date, start, end in shifts
        ],
    )
    work_days = [
        EstimateWorkDay(
            work_date=work_date,
            start=start,
            end=end,
            hours=shift_hours(start, end),
            status=work_status(work_date, end, now),
        )
        for work_date, start, end in shifts
        if period.first_day <= work_date <= period.last_day
    ]
    return PayrollEstimate(
        store_id=store.id,
        member_id=membership.id,
        staff_name=membership.staff_name,
        month=period.label,
        hourly_wage=membership.hourly_wage,
        payday=store.payday,
        tax_type=tax_type,
        weekly_allowance_enabled=True,
        work_days=work_days,
        result=result,
    )


class PayrollEstimateService:
    def __init__(
        self,
        repository: PayrollRepositoryProtocol,
        store_access: StoreAccessProtocol,
        clock: Callable[[], datetime] = lambda: datetime.now(UTC),
    ) -> None:
        """예상 급여 계산에 필요한 저장소, 권한 검사기, 시계를 받습니다."""
        self._repository = repository
        self._store_access = store_access
        self._clock = clock

    async def _estimates(
        self,
        store: Store,
        memberships: list[Membership],
        month: str | None,
    ) -> tuple[MonthPeriod, list[PayrollEstimate]]:
        """구성원들의 확정 근무를 한 번에 조회해 예상 급여를 계산합니다."""
        now = self._clock()
        period = parse_month(month, now)
        shifts = await self._repository.list_published_shift_times(
            store.id,
            [membership.id for membership in memberships],
            period.first_day - WEEK_MARGIN,
            period.last_day + WEEK_MARGIN,
        )
        estimates = [
            build_estimate(
                membership,
                store,
                period,
                shifts.get(membership.id, []),
                now,
            )
            for membership in memberships
        ]
        return period, estimates

    async def estimate_mine(
        self,
        store_id: UUID,
        user_id: UUID,
        month: str | None,
    ) -> PayrollEstimate:
        """확정 스케줄을 근거로 내 한 달 예상 급여를 계산합니다."""
        found = await self._repository.get_active_membership_with_store(
            store_id,
            user_id,
        )
        if found is None:
            await self._store_access.ensure_member(store_id, user_id)
            raise PayrollStaffOnlyError
        membership, store = found
        _, estimates = await self._estimates(store, [membership], month)
        return estimates[0]

    async def list_estimates(
        self,
        store_id: UUID,
        user_id: UUID,
        month: str | None,
    ) -> PayrollEstimateList:
        """사장님이 재직 중인 직원 전체의 예상 급여를 조회합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        found = await self._repository.list_active_memberships_with_store(store_id)
        if found is None:
            raise PayrollEstimateNotFoundError
        store, memberships = found
        period, estimates = await self._estimates(store, memberships, month)
        return PayrollEstimateList(store.id, period.label, store.payday, estimates)

    async def get_estimate(
        self,
        store_id: UUID,
        user_id: UUID,
        member_id: UUID,
        month: str | None,
    ) -> PayrollEstimate:
        """사장님은 모든 직원, 알바생은 본인의 예상 급여만 조회합니다."""
        found = await self._repository.get_active_membership_by_id(
            store_id,
            member_id,
        )
        if found is None or found[0].user_id != user_id:
            await self._store_access.ensure_owner(store_id, user_id)
        if found is None:
            raise PayrollEstimateNotFoundError
        membership, store = found
        _, estimates = await self._estimates(store, [membership], month)
        return estimates[0]
