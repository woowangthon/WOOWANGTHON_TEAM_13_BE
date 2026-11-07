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


MemberStatus = Literal["ACTIVE", "LEFT"]


class MemberResponse(MembershipSchema):
    member_id: UUID
    user_id: UUID
    staff_name: str
    role: str
    hourly_wage: int
    status: MemberStatus
    joined_at: datetime
    left_at: datetime | None


class MemberListResponse(MembershipSchema):
    members: list[MemberResponse]
