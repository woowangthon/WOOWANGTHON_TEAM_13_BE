from calendar import monthrange
from collections.abc import Callable
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
# 월을 걸친 주의 주휴수당을 계산하려고 앞뒤 6일을 함께 조회합니다.
WEEK_MARGIN = timedelta(days=6)


class PayrollStaffOnlyError(Exception):
    """구성원이 아닌 사장님이 내 예상 급여를 요청했을 때 발생합니다."""


class PayrollRepositoryProtocol(Protocol):
    async def get_active_membership_with_store(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> tuple[Membership, Store] | None: ...

    async def list_published_shift_times(
        self,
        store_id: UUID,
        membership_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[tuple[date, time, time]]: ...


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
    """알바생에게 보여 줄 한 달 예상 급여입니다."""

    store_id: UUID
    month: str
    hourly_wage: int
    payday: int | None
    tax_type: TaxType
    weekly_allowance_enabled: bool
    work_days: list[EstimateWorkDay]
    result: PayrollResult


def parse_month(month: str | None, now: datetime) -> tuple[int, int]:
    """YYYY-MM 문자열을 연·월로 바꾸고, 없으면 한국 시간 기준 이번 달을 씁니다."""
    if month is None:
        local = now.astimezone(SEOUL)
        return local.year, local.month
    year, month_number = month.split("-")
    return int(year), int(month_number)


def shift_hours(start: time, end: time) -> Decimal:
    """근무 시작·종료 시각으로 근무시간을 계산합니다."""
    minutes = (end.hour * 60 + end.minute) - (start.hour * 60 + start.minute)
    return Decimal(minutes) / Decimal(60)


def work_status(work_date: date, end: time, now: datetime) -> WorkStatus:
    """근무 종료 시각이 지났으면 worked, 아니면 planned를 반환합니다."""
    ended_at = datetime.combine(work_date, end, tzinfo=SEOUL)
    return "worked" if ended_at <= now else "planned"


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

        now = self._clock()
        year, month_number = parse_month(month, now)
        first_day = date(year, month_number, 1)
        last_day = date(year, month_number, monthrange(year, month_number)[1])
        shifts = await self._repository.list_published_shift_times(
            store_id,
            membership.id,
            first_day - WEEK_MARGIN,
            last_day + WEEK_MARGIN,
        )

        tax_type = cast(TaxType, membership.tax_type)
        result = calculate_payroll(
            year=year,
            month=month_number,
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
            if first_day <= work_date <= last_day
        ]
        return PayrollEstimate(
            store_id=store_id,
            month=f"{year:04d}-{month_number:02d}",
            hourly_wage=membership.hourly_wage,
            payday=store.payday,
            tax_type=tax_type,
            weekly_allowance_enabled=True,
            work_days=work_days,
            result=result,
        )
