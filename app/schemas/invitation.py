from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.membership import TaxType

INVITATION_CODE_PATTERN = r"^[A-HJ-NP-Z2-9]{6}$"
MINIMUM_HOURLY_WAGE_2026 = 10_320


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class InvitationSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class InvitationScheduleInput(InvitationSchema):
    template_id: UUID
    weekday: int = Field(ge=0, le=6)


def _reject_duplicate_schedule(
    value: list[InvitationScheduleInput],
) -> list[InvitationScheduleInput]:
    keys = [(item.template_id, item.weekday) for item in value]
    if len(keys) != len(set(keys)):
        raise ValueError("schedule must not contain duplicates")
    return value


class InvitationCreateRequest(InvitationSchema):
    staff_name: str = Field(min_length=1, max_length=50)
    hourly_wage: int = Field(ge=MINIMUM_HOURLY_WAGE_2026)
    tax_type: TaxType = "none"
    schedule: list[InvitationScheduleInput] = Field(
        default_factory=list,
        max_length=140,
    )

    @field_validator("staff_name")
    @classmethod
    def strip_staff_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("staffName must not be blank")
        return name

    @field_validator("schedule")
    @classmethod
    def reject_duplicate_schedule(
        cls, value: list[InvitationScheduleInput]
    ) -> list[InvitationScheduleInput]:
        return _reject_duplicate_schedule(value)


class InvitationUpdateRequest(InvitationSchema):
    tax_type: TaxType | None = None
    staff_name: str | None = Field(default=None, min_length=1, max_length=50)
    hourly_wage: int | None = Field(default=None, ge=MINIMUM_HOURLY_WAGE_2026)
    schedule: list[InvitationScheduleInput] | None = Field(
        default=None,
        max_length=140,
    )

    @field_validator("staff_name")
    @classmethod
    def strip_staff_name(cls, value: str | None) -> str | None:
        if value is None:
            return None
        name = value.strip()
        if not name:
            raise ValueError("staffName must not be blank")
        return name

    @field_validator("schedule")
    @classmethod
    def reject_duplicate_schedule(
        cls, value: list[InvitationScheduleInput] | None
    ) -> list[InvitationScheduleInput] | None:
        return _reject_duplicate_schedule(value) if value is not None else None

    @model_validator(mode="after")
    def require_change(self) -> "InvitationUpdateRequest":
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if "staff_name" in self.model_fields_set and self.staff_name is None:
            raise ValueError("staffName must not be null")
        if "hourly_wage" in self.model_fields_set and self.hourly_wage is None:
            raise ValueError("hourlyWage must not be null")
        if "tax_type" in self.model_fields_set and self.tax_type is None:
            raise ValueError("taxType must not be null")
        if "schedule" in self.model_fields_set and self.schedule is None:
            raise ValueError("schedule must not be null")
        return self


class InvitationResponse(InvitationSchema):
    invitation_id: UUID
    store_id: UUID
    code: str
    staff_name: str
    hourly_wage: int
    tax_type: TaxType
    schedule: list[InvitationScheduleInput]
    created_at: datetime


InvitationStatus = Literal["AVAILABLE", "USED", "REVOKED"]


class InvitationSummaryResponse(InvitationResponse):
    status: InvitationStatus
    accepted_at: datetime | None
    revoked_at: datetime | None


class InvitationListResponse(InvitationSchema):
    invitations: list[InvitationSummaryResponse]


class InvitationShareInfoResponse(InvitationSchema):
    invitation_id: UUID
    code: str
    deep_link: str


class InvitationCodeRequest(InvitationSchema):
    code: str = Field(pattern=INVITATION_CODE_PATTERN)

    @field_validator("code", mode="before")
    @classmethod
    def normalize_code(cls, value: object) -> object:
        if not isinstance(value, str):
            return value
        return value.strip().upper()


class InvitationStoreResponse(InvitationSchema):
    store_id: UUID
    name: str
    owner_name: str
    photo_url: str | None
    theme: None = None


class InvitationVerificationResponse(InvitationSchema):
    code: str
    staff_name: str
    store: InvitationStoreResponse


class MembershipResponse(InvitationSchema):
    store_id: UUID
    store_name: str
    member_id: UUID
    role: str
    staff_name: str
    joined_at: datetime
