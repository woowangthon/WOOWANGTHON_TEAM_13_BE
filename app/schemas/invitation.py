from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

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


class InvitationCreateRequest(InvitationSchema):
    staff_name: str = Field(min_length=1, max_length=50)
    hourly_wage: int = Field(ge=MINIMUM_HOURLY_WAGE_2026)

    @field_validator("staff_name")
    @classmethod
    def strip_staff_name(cls, value: str) -> str:
        name = value.strip()
        if not name:
            raise ValueError("staffName must not be blank")
        return name


class InvitationResponse(InvitationSchema):
    invitation_id: UUID
    store_id: UUID
    code: str
    staff_name: str
    hourly_wage: int
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
