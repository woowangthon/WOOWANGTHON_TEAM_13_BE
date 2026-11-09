import datetime as dt
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


def _to_camel(value: str) -> str:
    """응답 필드명을 camelCase로 변환합니다."""
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class PayrollSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class PayrollWorkDayResponse(PayrollSchema):
    date: dt.date
    start: str
    end: str
    hours: float
    status: Literal["worked", "planned"]


class PayrollWeekResponse(PayrollSchema):
    week_start: dt.date
    hours: float
    weekly_allowance_eligible: bool
    weekly_allowance: int


class PayrollEstimateResponse(PayrollSchema):
    store_id: UUID
    month: str
    hourly_wage: int
    payday: int | None
    tax_type: Literal["none", "3.3", "ins"]
    weekly_allowance_enabled: bool
    work_days: list[PayrollWorkDayResponse]
    hours: float
    base_pay: int
    weekly_allowance: int
    gross_pay: int
    deduction: int
    net_pay: int
    weeks: list[PayrollWeekResponse]
    ai_note: str | None
    is_estimate: bool
