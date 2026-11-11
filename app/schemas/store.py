from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.schemas.schedule import ShiftTemplateInput


def _validate_payday(value: int | None) -> int | None:
    if value is not None and not 1 <= value <= 31:
        raise ValueError("payday must be between 1 and 31")
    return value


def _to_camel(value: str) -> str:
    """응답 필드명을 camelCase로 변환합니다."""
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class StoreSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


BusinessSize = Literal["UNDER_FIVE", "FIVE_OR_MORE"]


def _validate_closed_weekdays(value: list[int] | None) -> list[int] | None:
    if value is None:
        return None
    if len(value) != len(set(value)):
        raise ValueError("closed weekdays must not contain duplicates")
    if any(day < 0 or day > 6 for day in value):
        raise ValueError("closed weekdays must be between 0 and 6")
    return sorted(value)


class StoreCreateRequest(StoreSchema):
    name: str = Field(min_length=1, max_length=100)
    address: str = Field(min_length=1, max_length=255)
    business_verification_id: int = Field(gt=0)
    photo_url: str | None = Field(default=None, max_length=2048)
    payday: int | None = None
    business_size: BusinessSize | None = None
    closed_weekdays: list[int] = Field(default_factory=list, max_length=7)
    closed_on_holidays: bool = False
    shift_templates: list[ShiftTemplateInput] = Field(
        default_factory=list,
        max_length=20,
    )

    @field_validator("shift_templates")
    @classmethod
    def reject_duplicate_template_names(
        cls, value: list[ShiftTemplateInput]
    ) -> list[ShiftTemplateInput]:
        names = [item.name for item in value]
        if len(names) != len(set(names)):
            raise ValueError("shift template names must be unique")
        return value

    @field_validator("name", "address")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        """필수 문자열의 앞뒤 공백과 빈 값을 검사합니다."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped

    @field_validator("photo_url")
    @classmethod
    def normalize_photo_url(cls, value: str | None) -> str | None:
        """빈 대표 이미지 URL을 null로 정규화합니다."""
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("payday")
    @classmethod
    def validate_payday(cls, value: int | None) -> int | None:
        return _validate_payday(value)

    @field_validator("closed_weekdays")
    @classmethod
    def validate_closed_weekdays(cls, value: list[int]) -> list[int]:
        return _validate_closed_weekdays(value) or []


class StoreUpdateRequest(StoreSchema):
    name: str | None = Field(default=None, max_length=100)
    address: str | None = Field(default=None, max_length=255)
    business_verification_id: int | None = Field(default=None, gt=0)
    photo_url: str | None = Field(default=None, max_length=2048)
    payday: int | None = None
    business_size: BusinessSize | None = None
    closed_weekdays: list[int] | None = Field(default=None, max_length=7)
    closed_on_holidays: bool | None = None

    @field_validator("name", "address")
    @classmethod
    def strip_optional_required_text(cls, value: str | None) -> str:
        """수정 요청에 포함된 필수 문자열 값을 검사합니다."""
        if value is None or not value.strip():
            raise ValueError("value must not be blank")
        return value.strip()

    @field_validator("photo_url")
    @classmethod
    def normalize_optional_photo_url(cls, value: str | None) -> str | None:
        """빈 대표 이미지 URL을 null로 정규화합니다."""
        if value is None:
            return None
        stripped = value.strip()
        return stripped or None

    @field_validator("payday")
    @classmethod
    def validate_payday(cls, value: int | None) -> int | None:
        return _validate_payday(value)

    @field_validator("closed_weekdays")
    @classmethod
    def validate_closed_weekdays(cls, value: list[int] | None) -> list[int] | None:
        return _validate_closed_weekdays(value)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "StoreUpdateRequest":
        """수정할 필드가 하나 이상인지 검사합니다."""
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        if (
            "business_verification_id" in self.model_fields_set
            and self.business_verification_id is None
        ):
            raise ValueError("business verification id must not be null")
        if "closed_weekdays" in self.model_fields_set and self.closed_weekdays is None:
            raise ValueError("closed weekdays must not be null")
        if (
            "closed_on_holidays" in self.model_fields_set
            and self.closed_on_holidays is None
        ):
            raise ValueError("closed on holidays must not be null")
        return self


class StoreResponse(StoreSchema):
    store_id: UUID
    name: str
    address: str
    owner_name: str
    business_verification_id: int | None
    photo_url: str | None
    payday: int | None
    business_size: BusinessSize | None
    closed_weekdays: list[int]
    closed_on_holidays: bool


class StoreListResponse(StoreSchema):
    stores: list[StoreResponse]
