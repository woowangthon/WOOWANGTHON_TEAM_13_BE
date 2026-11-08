from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

AvailabilityStatus = Literal["available", "unavailable"]


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


def parse_month(value: str) -> date:
    """YYYY-MM 문자열을 해당 월의 첫날로 변환합니다."""
    try:
        year_text, month_text = value.split("-", maxsplit=1)
        year = int(year_text)
        month = int(month_text)
        if len(year_text) != 4 or len(month_text) != 2:
            raise ValueError
        return date(year, month, 1)
    except (TypeError, ValueError) as exc:
        raise ValueError("month must use YYYY-MM format") from exc


class AvailabilitySchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class AvailabilityDayInput(AvailabilitySchema):
    date: date
    status: AvailabilityStatus


class AvailabilityInput(AvailabilitySchema):
    days: list[AvailabilityDayInput] = Field(default_factory=list, max_length=31)
    memo: str = Field(default="", max_length=500)

    @field_validator("memo")
    @classmethod
    def normalize_memo(cls, value: str) -> str:
        return value.strip()

    @field_validator("days")
    @classmethod
    def reject_duplicate_days(
        cls,
        value: list[AvailabilityDayInput],
    ) -> list[AvailabilityDayInput]:
        dates = [item.date for item in value]
        if len(dates) != len(set(dates)):
            raise ValueError("days must not contain duplicate dates")
        return sorted(value, key=lambda item: item.date)


class AvailabilityCreateRequest(AvailabilityInput):
    month: str

    @field_validator("month")
    @classmethod
    def validate_month(cls, value: str) -> str:
        parsed = parse_month(value)
        return f"{parsed.year:04d}-{parsed.month:02d}"

    @model_validator(mode="after")
    def validate_days_in_month(self) -> "AvailabilityCreateRequest":
        month = parse_month(self.month)
        if any(
            (item.date.year, item.date.month) != (month.year, month.month)
            for item in self.days
        ):
            raise ValueError("every day must belong to month")
        return self


class AvailabilityResponse(AvailabilitySchema):
    availability_id: UUID | None
    month: str
    deadline: date
    days: list[AvailabilityDayInput]
    memo: str
    submitted_at: datetime | None


class StoreAvailabilityItem(AvailabilityResponse):
    member_id: UUID
    staff_name: str


class StoreAvailabilityListResponse(AvailabilitySchema):
    month: str
    deadline: date
    availabilities: list[StoreAvailabilityItem]


class AvailabilitySubmissionItem(AvailabilitySchema):
    member_id: UUID
    staff_name: str
    submitted: bool
    submitted_at: datetime | None


class AvailabilitySubmissionListResponse(AvailabilitySchema):
    month: str
    deadline: date
    total_members: int
    submitted_count: int
    members: list[AvailabilitySubmissionItem]
