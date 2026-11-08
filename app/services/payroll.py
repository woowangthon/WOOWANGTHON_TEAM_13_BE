from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from decimal import ROUND_HALF_UP, Decimal
from typing import Literal

TaxType = Literal["none", "3.3", "ins"]

WEEKLY_ALLOWANCE_MIN_HOURS = Decimal(15)
FULL_TIME_WEEKLY_HOURS = Decimal(40)
FULL_TIME_DAILY_HOURS = Decimal(8)

# 2026년 근로자 부담분: 국민연금 4.75%, 건강 3.595%, 장기요양 0.4724%, 고용 0.9%
DEDUCTION_RATES: dict[TaxType, Decimal] = {
    "none": Decimal(0),
    "3.3": Decimal("0.033"),
    "ins": Decimal("0.097174"),
}


@dataclass(frozen=True, slots=True)
class PayrollWorkDay:
    """급여 계산에 쓰는 하루 근무 시간입니다."""

    work_date: date
    hours: Decimal


@dataclass(frozen=True, slots=True)
class PayrollWeek:
    """월요일에 시작하는 한 주의 주휴수당 근거입니다."""

    week_start: date
    hours: Decimal
    weekly_allowance_eligible: bool
    weekly_allowance: int


@dataclass(frozen=True, slots=True)
class PayrollResult:
    """한 달 예상 급여 계산 결과입니다."""

    hours: Decimal
    base_pay: int
    weekly_allowance: int
    gross_pay: int
    deduction: int
    net_pay: int
    weeks: list[PayrollWeek]


def round_won(amount: Decimal) -> int:
    """금액을 1원 단위로 반올림합니다."""
    return int(amount.quantize(Decimal(1), rounding=ROUND_HALF_UP))


def round_ten_won(amount: Decimal) -> int:
    """금액을 10원 단위로 반올림합니다."""
    return round_won(amount / 10) * 10


def calculate_weekly_allowance(hours: Decimal, hourly_wage: int) -> int:
    """주 근무시간으로 한 주의 주휴수당을 계산합니다."""
    if hours < WEEKLY_ALLOWANCE_MIN_HOURS:
        return 0
    paid_hours = min(hours, FULL_TIME_WEEKLY_HOURS)
    ratio = paid_hours / FULL_TIME_WEEKLY_HOURS
    return round_ten_won(ratio * FULL_TIME_DAILY_HOURS * hourly_wage)


def _week_start(day: date) -> date:
    """날짜가 속한 주의 월요일을 반환합니다."""
    return day - timedelta(days=day.weekday())


def _calculate_weeks(
    work_days: Iterable[PayrollWorkDay],
    year: int,
    month: int,
    hourly_wage: int,
    weekly_allowance_enabled: bool,
) -> list[PayrollWeek]:
    """일요일이 해당 월에 속한 주만 골라 주휴수당을 계산합니다."""
    hours_by_week: dict[date, Decimal] = defaultdict(Decimal)
    for day in work_days:
        hours_by_week[_week_start(day.work_date)] += day.hours

    weeks = []
    for week_start, hours in sorted(hours_by_week.items()):
        week_end = week_start + timedelta(days=6)
        if (week_end.year, week_end.month) != (year, month):
            continue
        allowance = (
            calculate_weekly_allowance(hours, hourly_wage)
            if weekly_allowance_enabled
            else 0
        )
        weeks.append(PayrollWeek(week_start, hours, allowance > 0, allowance))
    return weeks


def calculate_payroll(
    *,
    year: int,
    month: int,
    hourly_wage: int,
    tax_type: TaxType,
    weekly_allowance_enabled: bool,
    work_days: list[PayrollWorkDay],
) -> PayrollResult:
    """근무 기록으로 한 달 예상 급여를 규칙에 따라 계산합니다."""
    month_days = [
        day
        for day in work_days
        if (day.work_date.year, day.work_date.month) == (year, month)
    ]
    hours = sum((day.hours for day in month_days), Decimal(0))
    base_pay = round_won(hours * hourly_wage)
    weeks = _calculate_weeks(
        work_days,
        year,
        month,
        hourly_wage,
        weekly_allowance_enabled,
    )
    weekly_allowance = sum(week.weekly_allowance for week in weeks)
    gross_pay = base_pay + weekly_allowance
    deduction = round_ten_won(gross_pay * DEDUCTION_RATES[tax_type])
    return PayrollResult(
        hours=hours,
        base_pay=base_pay,
        weekly_allowance=weekly_allowance,
        gross_pay=gross_pay,
        deduction=deduction,
        net_pay=gross_pay - deduction,
        weeks=weeks,
    )
