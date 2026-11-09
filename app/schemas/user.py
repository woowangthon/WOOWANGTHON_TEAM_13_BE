from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_camel(value: str) -> str:
    """응답 필드명을 camelCase로 변환합니다."""
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class UserSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class StoreSummary(UserSchema):
    store_id: UUID
    store_name: str
    role: Literal["owner", "staff"]
    owner_name: str
    staff_name: str | None
    photo_url: str | None


class MyStoreDetail(UserSchema):
    store_id: UUID
    name: str
    kind: str | None = None
    address: str
    owner_name: str
    role: Literal["owner", "staff"]
    member_id: UUID | None
    staff_name: str | None
    photo_url: str | None
    theme: str | None = None
    joined_at: datetime


class MyStoreListResponse(UserSchema):
    stores: list[MyStoreDetail] = Field(default_factory=list)


class UserResponse(UserSchema):
    user_id: UUID
    nickname: str
    email: str | None
    provider: str
    stores: list[StoreSummary] = Field(default_factory=list)


class UserUpdateRequest(UserSchema):
    nickname: str = Field(min_length=1, max_length=50)

    @field_validator("nickname")
    @classmethod
    def strip_and_validate_nickname(cls, value: str) -> str:
        """닉네임의 앞뒤 공백과 빈 값을 검사합니다."""
        nickname = value.strip()
        if not nickname:
            raise ValueError("nickname must not be blank")
        return nickname
