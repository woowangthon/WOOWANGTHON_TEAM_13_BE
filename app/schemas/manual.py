from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

ManualIcon = Literal[
    "wifi",
    "restroom",
    "open",
    "close",
    "delivery",
    "refund",
    "milk",
    "umbrella",
]
MANUAL_BODY_MAX_LENGTH = 5000


def _to_camel(value: str) -> str:
    """응답 필드명을 camelCase로 변환합니다."""
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


def _strip_required(value: str | None) -> str:
    """필수 문자열의 앞뒤 공백을 제거하고 빈 값을 거부합니다."""
    if value is None or not value.strip():
        raise ValueError("value must not be blank")
    return value.strip()


class ManualSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class ManualCategoryCreateRequest(ManualSchema):
    name: str = Field(min_length=1, max_length=50)

    @field_validator("name")
    @classmethod
    def strip_name(cls, value: str) -> str:
        """카테고리 이름의 공백을 검사합니다."""
        return _strip_required(value)


class ManualCategoryResponse(ManualSchema):
    category_id: UUID
    name: str


class ManualCreateRequest(ManualSchema):
    title: str = Field(min_length=1, max_length=100)
    body: str = Field(min_length=1, max_length=MANUAL_BODY_MAX_LENGTH)
    category_id: UUID | None = None
    icon: ManualIcon | None = None

    @field_validator("title", "body")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        """필수 문자열의 공백을 검사합니다."""
        return _strip_required(value)


class ManualUpdateRequest(ManualSchema):
    title: str | None = Field(default=None, max_length=100)
    body: str | None = Field(default=None, max_length=MANUAL_BODY_MAX_LENGTH)
    category_id: UUID | None = None
    icon: ManualIcon | None = None

    @field_validator("title", "body")
    @classmethod
    def strip_optional_required_text(cls, value: str | None) -> str:
        """수정 요청에 포함된 필수 문자열 값을 검사합니다."""
        return _strip_required(value)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "ManualUpdateRequest":
        """수정할 필드가 하나 이상인지 검사합니다."""
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class ManualResponse(ManualSchema):
    manual_id: UUID
    category_id: UUID | None
    icon: str | None
    title: str
    body: str
    is_new: bool
    updated_at: datetime


class ManualListResponse(ManualSchema):
    manuals: list[ManualResponse]


class ManualRecommendationRequest(ManualSchema):
    keywords: list[str] = Field(default_factory=list, max_length=20)


class ManualRecommendation(ManualSchema):
    icon: str
    title: str
    body: str


class ManualRecommendationListResponse(ManualSchema):
    recommendations: list[ManualRecommendation]
