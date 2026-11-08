from datetime import date
from decimal import Decimal

import pytest

from app.services.payroll import (
    PayrollResult,
    PayrollWorkDay,
    TaxType,
    calculate_payroll,
    calculate_weekly_allowance,
    round_ten_won,
)

WAGE = 10320


def day(month: int, value: int, hours: str = "5") -> PayrollWorkDay:
    return PayrollWorkDay(date(2026, month, value), Decimal(hours))


def calculate(
    work_days: list[PayrollWorkDay],
    tax_type: TaxType = "none",
    weekly_allowance_enabled: bool = True,
) -> PayrollResult:
    return calculate_payroll(
        year=2026,
        month=11,
        hourly_wage=WAGE,
        tax_type=tax_type,
        weekly_allowance_enabled=weekly_allowance_enabled,
        work_days=work_days,
    )


def fe_example_days() -> list[PayrollWorkDay]:
    return [
        day(11, 2, "4"),
        day(11, 4, "4"),
        day(11, 6, "4"),
        day(11, 9),
        day(11, 11),
        day(11, 13),
        day(11, 16),
        day(11, 18),
        day(11, 20),
        day(11, 23),
        day(11, 25),
        day(11, 27),
    ]


def test_matches_fe_proposal_example() -> None:
    result = calculate(fe_example_days(), tax_type="3.3")

    assert result.hours == Decimal(57)
    assert result.base_pay == 588240
    assert result.weekly_allowance == 92880
    assert result.gross_pay == 681120
    assert result.deduction == 22480
    assert result.net_pay == 658640
    assert [week.week_start for week in result.weeks] == [
        date(2026, 11, 2),
        date(2026, 11, 9),
        date(2026, 11, 16),
        date(2026, 11, 23),
    ]
    assert [week.weekly_allowance_eligible for week in result.weeks] == [
        False,
        True,
        True,
        True,
    ]


@pytest.mark.parametrize(
    ("hours", "expected"),
    [
        ("14.5", 0),
        ("15", 30960),
        ("20", 41280),
        ("40", 82560),
        ("48", 82560),
    ],
)
def test_weekly_allowance_boundaries(hours: str, expected: int) -> None:
    assert calculate_weekly_allowance(Decimal(hours), WAGE) == expected


def test_disabled_weekly_allowance_keeps_base_pay() -> None:
    result = calculate([day(11, 9, "15")], weekly_allowance_enabled=False)

    assert result.base_pay == 154800
    assert result.weekly_allowance == 0
    assert result.weeks[0].weekly_allowance_eligible is False


def test_week_belongs_to_month_of_its_sunday() -> None:
    result = calculate(
        [
            day(10, 30, "10"),
            day(11, 1, "5"),
            day(11, 30, "10"),
            day(12, 2, "5"),
        ]
    )

    assert result.hours == Decimal(15)
    assert [week.week_start for week in result.weeks] == [date(2026, 10, 26)]
    assert result.weeks[0].hours == Decimal(15)
    assert result.weekly_allowance == 30960


def test_half_hours_do_not_use_float() -> None:
    result = calculate([day(11, 2, "4.5")])

    assert result.base_pay == 46440


@pytest.mark.parametrize(
    ("tax_type", "deduction"),
    [("none", 0), ("3.3", 33000), ("ins", 97170)],
)
def test_deduction_is_rounded_to_ten_won(tax_type: TaxType, deduction: int) -> None:
    result = calculate_payroll(
        year=2026,
        month=11,
        hourly_wage=10000,
        tax_type=tax_type,
        weekly_allowance_enabled=False,
        work_days=[day(11, 2, "100")],
    )

    assert result.deduction == deduction
    assert result.net_pay == 1000000 - deduction


def test_round_ten_won_rounds_half_up() -> None:
    assert round_ten_won(Decimal(15)) == 20
    assert round_ten_won(Decimal(14)) == 10


def test_no_work_days_is_zero() -> None:
    result = calculate([])

    assert result.net_pay == 0
    assert result.weeks == []
