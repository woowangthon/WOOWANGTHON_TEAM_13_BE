from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

RecipeTemp = Literal["ICE", "HOT", "DESSERT"]


def _to_camel(value: str) -> str:
    """응답 필드명을 camelCase로 변환합니다."""
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


def _strip_required(value: str | None) -> str:
    """필수 문자열의 앞뒤 공백을 제거하고 빈 값을 거부합니다."""
    if value is None or not value.strip():
        raise ValueError("value must not be blank")
    return value.strip()


def _strip_optional(value: str | None) -> str | None:
    """선택 문자열의 공백을 제거하고 빈 값을 null로 정규화합니다."""
    if value is None:
        return None
    return value.strip() or None


def _strip_steps(steps: list[str] | None) -> list[str]:
    """조리 순서의 각 항목을 검사합니다."""
    if steps is None:
        raise ValueError("value must not be null")
    return [_strip_required(step) for step in steps]


class RecipeSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class RecipeIngredient(RecipeSchema):
    name: str = Field(min_length=1, max_length=100)
    amount: str = Field(min_length=1, max_length=50)

    @field_validator("name", "amount")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        """재료 문자열의 공백을 검사합니다."""
        return _strip_required(value)


class RecipeCreateRequest(RecipeSchema):
    name: str = Field(min_length=1, max_length=100)
    category: str = Field(min_length=1, max_length=50)
    temp: RecipeTemp | None = None
    size: str | None = Field(default=None, max_length=20)
    ingredients: list[RecipeIngredient] = Field(default_factory=list)
    steps: list[str] = Field(default_factory=list)
    memo: str | None = None

    @field_validator("name", "category")
    @classmethod
    def strip_required_text(cls, value: str) -> str:
        """필수 문자열의 공백을 검사합니다."""
        return _strip_required(value)

    @field_validator("size", "memo")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        """선택 문자열을 정규화합니다."""
        return _strip_optional(value)

    @field_validator("steps")
    @classmethod
    def strip_steps(cls, value: list[str]) -> list[str]:
        """조리 순서를 검사합니다."""
        return _strip_steps(value)


class RecipeUpdateRequest(RecipeSchema):
    name: str | None = Field(default=None, max_length=100)
    category: str | None = Field(default=None, max_length=50)
    temp: RecipeTemp | None = None
    size: str | None = Field(default=None, max_length=20)
    ingredients: list[RecipeIngredient] | None = None
    steps: list[str] | None = None
    memo: str | None = None

    @field_validator("name", "category")
    @classmethod
    def strip_required_text(cls, value: str | None) -> str:
        """수정 요청에 포함된 필수 문자열을 검사합니다."""
        return _strip_required(value)

    @field_validator("size", "memo")
    @classmethod
    def strip_optional_text(cls, value: str | None) -> str | None:
        """선택 문자열을 정규화합니다."""
        return _strip_optional(value)

    @field_validator("ingredients")
    @classmethod
    def reject_null_ingredients(
        cls,
        value: list[RecipeIngredient] | None,
    ) -> list[RecipeIngredient]:
        """재료 목록을 null로 바꾸지 못하게 합니다."""
        if value is None:
            raise ValueError("value must not be null")
        return value

    @field_validator("steps")
    @classmethod
    def strip_steps(cls, value: list[str] | None) -> list[str]:
        """조리 순서를 검사합니다."""
        return _strip_steps(value)

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "RecipeUpdateRequest":
        """수정할 필드가 하나 이상인지 검사합니다."""
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class RecipeSummaryResponse(RecipeSchema):
    recipe_id: UUID
    name: str
    category: str
    temp: str | None
    size: str | None
    ingredients: list[RecipeIngredient]
    is_new: bool
    updated_at: datetime


class RecipeResponse(RecipeSummaryResponse):
    steps: list[str]
    memo: str | None


class RecipeCategorySummary(RecipeSchema):
    name: str
    count: int


class RecipeListResponse(RecipeSchema):
    categories: list[RecipeCategorySummary]
    default_category: str | None
    recipes: list[RecipeSummaryResponse]
