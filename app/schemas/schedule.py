from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


def _valid_time(value: str) -> str:
    parts = value.split(":")
    if len(parts) != 2:
        raise ValueError("time must use HH:MM format")
    try:
        hour, minute = (int(part) for part in parts)
    except ValueError as exc:
        raise ValueError("time must use HH:MM format") from exc
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("time must use HH:MM format")
    return f"{hour:02d}:{minute:02d}"


class ScheduleSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class RecommendationRules(ScheduleSchema):
    maximum_weekly_hours: int = Field(default=40, ge=1, le=168)
    minimum_rest_minutes: int = Field(default=30, ge=0, le=1440)


class RecommendationShiftInput(ScheduleSchema):
    date: date
    start: str
    end: str
    role: str = Field(default="", max_length=50)
    required_staff: int = Field(default=1, ge=1, le=20)

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: str) -> str:
        return _valid_time(value)

    @field_validator("role")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        return value.strip()

    @model_validator(mode="after")
    def validate_range(self) -> "RecommendationShiftInput":
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        return self


class RecommendationCreateRequest(ScheduleSchema):
    start_date: date
    end_date: date
    recommendation_count: int = Field(default=3, ge=1, le=3)
    shifts: list[RecommendationShiftInput] = Field(min_length=1, max_length=100)
    rules: RecommendationRules = Field(default_factory=RecommendationRules)

    @model_validator(mode="after")
    def validate_period_and_shifts(self) -> "RecommendationCreateRequest":
        if self.end_date < self.start_date:
            raise ValueError("endDate must not be before startDate")
        if (self.end_date - self.start_date).days > 30:
            raise ValueError("schedule period must not exceed 31 days")
        if any(
            item.date < self.start_date or item.date > self.end_date
            for item in self.shifts
        ):
            raise ValueError("every shift date must belong to the requested period")
        keys = [(item.date, item.start, item.end, item.role) for item in self.shifts]
        if len(keys) != len(set(keys)):
            raise ValueError("shifts must not contain duplicates")
        return self


class ScheduleAssignmentResponse(ScheduleSchema):
    member_id: UUID
    staff_name: str


class RecommendationShiftResponse(ScheduleSchema):
    shift_id: UUID
    date: date
    start: str
    end: str
    role: str
    required_staff: int
    assignments: list[ScheduleAssignmentResponse]


class RecommendationSummaryResponse(ScheduleSchema):
    recommendation_id: UUID
    batch_id: UUID
    candidate_no: int
    start_date: date
    end_date: date
    unfilled_slots: int
    created_at: datetime


class RecommendationDetailResponse(RecommendationSummaryResponse):
    rules: RecommendationRules
    shifts: list[RecommendationShiftResponse]
    warnings: list[str]


class RecommendationCreateResponse(ScheduleSchema):
    batch_id: UUID
    recommendations: list[RecommendationDetailResponse]


class RecommendationListResponse(ScheduleSchema):
    recommendations: list[RecommendationSummaryResponse]


class ScheduleCreateRequest(ScheduleSchema):
    recommendation_id: UUID
    name: str = Field(min_length=1, max_length=100)
    publish: bool = False

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized


class ScheduleShiftUpdate(ScheduleSchema):
    date: date
    start: str
    end: str
    role: str = Field(default="", max_length=50)
    assigned_member_ids: list[UUID] = Field(default_factory=list, max_length=20)

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: str) -> str:
        return _valid_time(value)

    @field_validator("role")
    @classmethod
    def normalize_role(cls, value: str) -> str:
        return value.strip()

    @field_validator("assigned_member_ids")
    @classmethod
    def validate_member_ids(cls, value: list[UUID]) -> list[UUID]:
        if len(value) != len(set(value)):
            raise ValueError("assignedMemberIds must not contain duplicates")
        return value

    @model_validator(mode="after")
    def validate_range(self) -> "ScheduleShiftUpdate":
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        return self


class ScheduleUpdateRequest(ScheduleSchema):
    name: str | None = Field(default=None, min_length=1, max_length=100)
    publish: bool | None = None
    shifts: list[ScheduleShiftUpdate] | None = Field(default=None, max_length=100)

    @field_validator("name")
    @classmethod
    def normalize_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = value.strip()
        if not normalized:
            raise ValueError("name must not be blank")
        return normalized

    @model_validator(mode="after")
    def require_change(self) -> "ScheduleUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class ScheduleShiftResponse(ScheduleSchema):
    shift_id: UUID
    date: date
    start: str
    end: str
    role: str
    assignments: list[ScheduleAssignmentResponse]


class ScheduleResponse(ScheduleSchema):
    schedule_id: UUID
    recommendation_id: UUID | None
    name: str
    start_date: date
    end_date: date
    status: Literal["draft", "published"]
    published_at: datetime | None
    shifts: list[ScheduleShiftResponse]
    created_at: datetime
    updated_at: datetime


class ScheduleListResponse(ScheduleSchema):
    schedules: list[ScheduleResponse]


class MyScheduleShiftResponse(ScheduleSchema):
    shift_id: UUID
    date: date
    start: str
    end: str
    role: str
    crew: list[str]


class MyScheduleResponse(ScheduleSchema):
    today: date
    week_start: date
    week_hours: float
    weekly_allowance_hours: int = 15
    week_note: str
    shifts: list[MyScheduleShiftResponse]
