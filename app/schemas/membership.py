from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class MembershipSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


TaxType = Literal["none", "3.3", "ins"]
MemberStatus = Literal["INVITED", "ACTIVE", "LEFT"]


class MemberResponse(MembershipSchema):
    member_id: UUID | None
    invitation_id: UUID | None
    user_id: UUID | None
    staff_name: str
    role: str
    hourly_wage: int
    tax_type: TaxType | None
    status: MemberStatus
    invited_at: datetime | None
    joined_at: datetime | None
    left_at: datetime | None


class MemberListResponse(MembershipSchema):
    members: list[MemberResponse]


class HourlyWageUpdateRequest(MembershipSchema):
    hourly_wage: int


class HourlyWageUpdateResponse(MembershipSchema):
    member_id: UUID
    hourly_wage: int
    updated_at: datetime
