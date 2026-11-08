from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_camel(value: str) -> str:
    """응답 필드명을 camelCase로 변환합니다."""
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class OwnerQuestionSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class OwnerQuestionAnswerRequest(OwnerQuestionSchema):
    answer: str = Field(min_length=1, max_length=2000)
    add_to_manual: bool = False
    manual_title: str | None = Field(default=None, max_length=100)

    @field_validator("answer")
    @classmethod
    def strip_answer(cls, value: str) -> str:
        """답변의 공백을 검사합니다."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class OwnerQuestionItem(OwnerQuestionSchema):
    question_id: UUID
    store_id: UUID
    title: str
    question: str
    icon: str | None
    staff_name: str
    asked_at: datetime
    status: str
    answer: str | None
    answered_at: datetime | None


class OwnerQuestionListResponse(OwnerQuestionSchema):
    questions: list[OwnerQuestionItem]
