from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


def _valid_time(value: str) -> str:
    try:
        hour_text, minute_text = value.split(":", maxsplit=1)
        hour, minute = int(hour_text), int(minute_text)
    except (TypeError, ValueError) as exc:
        raise ValueError("time must use HH:MM format") from exc
    if len(hour_text) != 2 or len(minute_text) != 2:
        raise ValueError("time must use HH:MM format")
    if not 0 <= hour <= 23 or not 0 <= minute <= 59:
        raise ValueError("time must use HH:MM format")
    return f"{hour:02d}:{minute:02d}"


class FixedScheduleSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ShiftTemplateInput(FixedScheduleSchema):
    name: str = Field(min_length=1, max_length=50)
    start: str
    end: str
    role: str = Field(default="", max_length=50)
    sort_order: int = Field(default=0, ge=0, le=100)

    @field_validator("name", "role")
    @classmethod
    def strip_text(cls, value: str) -> str:
        return value.strip()

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: str) -> str:
        return _valid_time(value)

    @model_validator(mode="after")
    def validate_range(self) -> "ShiftTemplateInput":
        if not self.name:
            raise ValueError("name must not be blank")
        if self.end <= self.start:
            raise ValueError("end must be later than start")
        return self


class ShiftTemplateCreateRequest(ShiftTemplateInput):
    pass


class ShiftTemplateUpdateRequest(FixedScheduleSchema):
    name: str | None = Field(default=None, min_length=1, max_length=50)
    start: str | None = None
    end: str | None = None
    role: str | None = Field(default=None, max_length=50)
    sort_order: int | None = Field(default=None, ge=0, le=100)

    @field_validator("name", "role")
    @classmethod
    def strip_text(cls, value: str | None) -> str | None:
        return value.strip() if value is not None else None

    @field_validator("start", "end")
    @classmethod
    def validate_time(cls, value: str | None) -> str | None:
        return _valid_time(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "ShiftTemplateUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if self.name == "":
            raise ValueError("name must not be blank")
        return self


class ShiftTemplateResponse(FixedScheduleSchema):
    template_id: UUID
    name: str
    start: str
    end: str
    role: str
    sort_order: int


class ShiftTemplateListResponse(FixedScheduleSchema):
    templates: list[ShiftTemplateResponse]


WorkerRole = Literal["owner", "staff"]


class ScheduleWorkerResponse(FixedScheduleSchema):
    user_id: UUID
    member_id: UUID | None
    name: str
    role: WorkerRole


class ScheduleWorkerListResponse(FixedScheduleSchema):
    workers: list[ScheduleWorkerResponse]


class FixedAssignmentInput(FixedScheduleSchema):
    template_id: UUID
    weekday: int = Field(ge=0, le=6)
    assignee_user_id: UUID


class FixedScheduleReplaceRequest(FixedScheduleSchema):
    assignments: list[FixedAssignmentInput] = Field(max_length=200)

    @field_validator("assignments")
    @classmethod
    def reject_duplicates(
        cls, value: list[FixedAssignmentInput]
    ) -> list[FixedAssignmentInput]:
        keys = [
            (item.template_id, item.weekday, item.assignee_user_id) for item in value
        ]
        if len(keys) != len(set(keys)):
            raise ValueError("assignments must not contain duplicates")
        return value


class FixedAssignmentResponse(FixedScheduleSchema):
    assignment_id: UUID
    template: ShiftTemplateResponse
    weekday: int
    assignee: ScheduleWorkerResponse


class FixedScheduleResponse(FixedScheduleSchema):
    assignments: list[FixedAssignmentResponse]


class CalendarShiftResponse(FixedScheduleSchema):
    assignment_id: UUID
    template_id: UUID
    date: date
    name: str
    start: str
    end: str
    role: str
    assignee: ScheduleWorkerResponse
    substituted: bool


class ScheduleCalendarResponse(FixedScheduleSchema):
    start_date: date
    end_date: date
    shifts: list[CalendarShiftResponse]


class SubstituteRequestCreate(FixedScheduleSchema):
    assignment_id: UUID
    date: date
    target_user_id: UUID


SubstituteRequestStatus = Literal["PENDING", "ACCEPTED", "REJECTED", "CANCELLED"]


class SubstituteRequestResponse(FixedScheduleSchema):
    request_id: UUID
    status: SubstituteRequestStatus
    date: date
    assignment_id: UUID
    shift_name: str
    start: str
    end: str
    requester: ScheduleWorkerResponse
    target: ScheduleWorkerResponse
    is_read: bool
    created_at: datetime
    responded_at: datetime | None


class SubstituteRequestListResponse(FixedScheduleSchema):
    requests: list[SubstituteRequestResponse]
