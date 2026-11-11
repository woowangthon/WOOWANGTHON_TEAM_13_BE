from datetime import date, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

HandoverTag = Literal["credit", "stock", "etc"]


def _to_camel(value: str) -> str:
    """응답 필드명을 camelCase로 변환합니다."""
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


def _strip_required(value: str) -> str:
    """필수 문자열의 앞뒤 공백을 제거하고 빈 값을 거부합니다."""
    stripped = value.strip()
    if not stripped:
        raise ValueError("value must not be blank")
    return stripped


class HandoverSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class HandoverDraftRequest(HandoverSchema):
    text: str = Field(min_length=1, max_length=2000)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """줄글의 공백을 검사합니다."""
        return _strip_required(value)


class HandoverItemInput(HandoverSchema):
    tag: HandoverTag
    text: str = Field(min_length=1, max_length=500)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """항목 내용의 공백을 검사합니다."""
        return _strip_required(value)


class HandoverItemUpdate(HandoverItemInput):
    item_id: UUID | None = None


class HandoverDraftResponse(HandoverSchema):
    summary: str
    items: list[HandoverItemInput]


class HandoverNoteCreateRequest(HandoverSchema):
    raw_text: str = Field(default="", max_length=2000)
    no_issue: bool = False
    summary: str = Field(default="", max_length=1000)
    items: list[HandoverItemInput] = Field(default_factory=list, max_length=50)

    @model_validator(mode="after")
    def normalize_no_issue(self) -> "HandoverNoteCreateRequest":
        """특이사항 없음이면 내용을 비우고, 아니면 항목을 요구합니다."""
        if self.no_issue:
            self.raw_text = ""
            self.summary = ""
            self.items = []
        elif not self.items:
            raise ValueError("items must not be empty")
        return self


class HandoverNoteUpdateRequest(HandoverSchema):
    raw_text: str | None = Field(default=None, max_length=2000)
    summary: str | None = Field(default=None, max_length=1000)
    items: list[HandoverItemUpdate] | None = Field(default=None, max_length=50)

    @field_validator("raw_text", "summary", "items")
    @classmethod
    def reject_null(cls, value: object) -> object:
        """수정 요청에서 null을 거부합니다."""
        if value is None:
            raise ValueError("value must not be null")
        return value

    @model_validator(mode="after")
    def require_at_least_one_field(self) -> "HandoverNoteUpdateRequest":
        """수정할 필드가 하나 이상인지 검사합니다."""
        if not self.model_fields_set:
            raise ValueError("at least one field must be provided")
        return self


class HandoverConfirmationRequest(HandoverSchema):
    item_id: UUID | None = None
    checked: bool = True


class HandoverUser(HandoverSchema):
    user_id: UUID
    name: str


class HandoverItemResponse(HandoverSchema):
    item_id: UUID
    tag: str
    text: str
    checked: bool
    checked_by: HandoverUser | None
    checked_at: datetime | None


class HandoverNoteResponse(HandoverSchema):
    note_id: UUID
    author: HandoverUser
    created_at: datetime
    updated_at: datetime
    raw_text: str
    no_issue: bool
    summary: str
    items: list[HandoverItemResponse]


class HandoverNoteListResponse(HandoverSchema):
    work_date: date = Field(alias="date")
    notes: list[HandoverNoteResponse]


class HandoverSummaryResponse(HandoverSchema):
    date: date
    summary: str | None
    note_count: int
