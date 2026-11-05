from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_camel(value: str) -> str:
    """응답 필드명을 camelCase로 변환합니다."""
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class AssistantChatSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class AssistantMessageCreateRequest(AssistantChatSchema):
    text: str = Field(min_length=1, max_length=1000)

    @field_validator("text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        """질문의 공백을 검사합니다."""
        stripped = value.strip()
        if not stripped:
            raise ValueError("value must not be blank")
        return stripped


class AssistantSource(AssistantChatSchema):
    kind: str
    id: UUID
    title: str


class AssistantMessageResponse(AssistantChatSchema):
    message_id: UUID
    sender: str
    text: str
    answer_type: str | None
    sources: list[AssistantSource]
    can_ask_owner: bool
    owner_question: dict[str, str] | None
    created_at: datetime


class AssistantExchangeResponse(AssistantChatSchema):
    question: AssistantMessageResponse
    answer: AssistantMessageResponse


class AssistantMessageListResponse(AssistantChatSchema):
    chat_id: UUID
    has_more: bool
    messages: list[AssistantMessageResponse]


class AssistantChatSummary(AssistantChatSchema):
    chat_id: UUID
    store_id: UUID
    created_at: datetime
    last_message_at: datetime
    last_message_text: str | None


class AssistantChatDetailResponse(AssistantChatSummary):
    suggestions: list[str]
    messages: list[AssistantMessageResponse]


class AssistantChatListResponse(AssistantChatSchema):
    suggestions: list[str]
    chats: list[AssistantChatSummary]
