from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Protocol
from uuid import UUID

from app.models.assistant_chat import AssistantChat, AssistantMessage
from app.models.owner_question import (
    OWNER_QUESTION_ANSWERED,
    OWNER_QUESTION_ASKED,
    OwnerQuestion,
)
from app.services.assistant_chat import (
    NOT_FOUND,
    AssistantChatNotFoundError,
    AssistantMessageNotFoundError,
)
from app.services.store_access import StoreAccessProtocol

ASKED_SYSTEM_TEXT = "사장님께 전달했어요"
TITLE_MAX_LENGTH = 30


class OwnerQuestionNotAllowedError(Exception):
    """찾지 못한 AI 답변이 아닌 메시지로 질문하려 할 때 발생합니다."""


class OwnerQuestionAlreadySentError(Exception):
    """이미 사장님께 물어본 답변일 때 발생합니다."""


class OwnerQuestionNotFoundError(Exception):
    """매장에서 질문을 찾지 못했을 때 발생합니다."""


class OwnerQuestionAlreadyAnsweredError(Exception):
    """이미 답변한 질문에 다시 답하려 할 때 발생합니다."""


class AddToManualNotSupportedError(Exception):
    """아직 지원하지 않는 매뉴얼 추가를 요청했을 때 발생합니다."""


@dataclass(frozen=True, slots=True)
class OwnerQuestionView:
    """질문과 질문한 직원 이름입니다."""

    question: OwnerQuestion
    staff_name: str


class ChatLookupProtocol(Protocol):
    async def get_chat(
        self,
        chat_id: UUID,
        store_id: UUID,
        user_id: UUID,
    ) -> AssistantChat | None: ...

    async def get_message(
        self,
        message_id: UUID,
        chat_id: UUID,
    ) -> AssistantMessage | None: ...

    async def get_previous_staff_message(
        self,
        message: AssistantMessage,
    ) -> AssistantMessage | None: ...


class OwnerQuestionRepositoryProtocol(Protocol):
    async def list_by_message_ids(
        self,
        message_ids: list[UUID],
    ) -> list[OwnerQuestion]: ...

    async def list_by_store_id(
        self,
        store_id: UUID,
        status: str | None,
    ) -> list[tuple[OwnerQuestion, str]]: ...

    async def get_by_id_and_store_id(
        self,
        question_id: UUID,
        store_id: UUID,
    ) -> tuple[OwnerQuestion, str] | None: ...

    async def get_chat(self, chat_id: UUID) -> AssistantChat | None: ...

    async def save_asked(
        self,
        question: OwnerQuestion,
        system_message: AssistantMessage,
        chat: AssistantChat,
    ) -> bool: ...

    async def save_answer(
        self,
        question: OwnerQuestion,
        answered_by: UUID,
        answered_at: datetime,
        owner_message: AssistantMessage,
        chat: AssistantChat,
    ) -> bool: ...


def question_title(question: str) -> str:
    """질문 앞부분으로 사장님 목록의 제목을 만듭니다."""
    text = " ".join(question.split())
    if len(text) <= TITLE_MAX_LENGTH:
        return text
    return text[:TITLE_MAX_LENGTH].rstrip() + "…"


def _after(previous: datetime) -> datetime:
    """이전 메시지보다 늦은 현재 시각을 만들어 내역 순서를 지킵니다."""
    now = datetime.now(UTC)
    return max(now, previous + timedelta(microseconds=1))


class OwnerQuestionService:
    def __init__(
        self,
        chats: ChatLookupProtocol,
        repository: OwnerQuestionRepositoryProtocol,
        store_access: StoreAccessProtocol,
    ) -> None:
        """사장님께 물어보기에 필요한 저장소와 권한 확인을 받습니다."""
        self._chats = chats
        self._repository = repository
        self._store_access = store_access

    async def questions_for_messages(
        self,
        messages: list[AssistantMessage],
    ) -> dict[UUID, OwnerQuestion]:
        """권한 확인을 마친 메시지에 연결된 질문을 메시지 ID별로 묶습니다."""
        ai_ids = [message.id for message in messages if message.sender == "ai"]
        questions = await self._repository.list_by_message_ids(ai_ids)
        return {question.message_id: question for question in questions}

    async def ask(
        self,
        store_id: UUID,
        chat_id: UUID,
        message_id: UUID,
        user_id: UUID,
    ) -> tuple[OwnerQuestion, AssistantMessage]:
        """찾지 못한 AI 답변의 원래 질문을 사장님께 넘깁니다."""
        await self._store_access.ensure_member(store_id, user_id)
        chat = await self._chats.get_chat(chat_id, store_id, user_id)
        if chat is None:
            raise AssistantChatNotFoundError
        answer = await self._chats.get_message(message_id, chat_id)
        if answer is None:
            raise AssistantMessageNotFoundError
        if answer.sender != "ai" or answer.answer_type != NOT_FOUND:
            raise OwnerQuestionNotAllowedError
        if await self._repository.list_by_message_ids([answer.id]):
            raise OwnerQuestionAlreadySentError
        original = await self._chats.get_previous_staff_message(answer)
        if original is None:
            raise OwnerQuestionNotAllowedError

        asked_at = _after(chat.last_message_at)
        question = OwnerQuestion(
            store_id=store_id,
            chat_id=chat.id,
            message_id=answer.id,
            asked_by=user_id,
            question=original.text,
            status=OWNER_QUESTION_ASKED,
            created_at=asked_at,
        )
        system_message = AssistantMessage(
            chat_id=chat.id,
            sender="system",
            text=ASKED_SYSTEM_TEXT,
            sources=[],
            created_at=asked_at,
        )
        chat.last_message_at = asked_at
        chat.last_message_text = ASKED_SYSTEM_TEXT
        if not await self._repository.save_asked(question, system_message, chat):
            raise OwnerQuestionAlreadySentError
        return question, system_message

    async def list_questions(
        self,
        store_id: UUID,
        user_id: UUID,
        status: str | None,
    ) -> list[OwnerQuestionView]:
        """사장님이 매장에 들어온 질문을 조회합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        rows = await self._repository.list_by_store_id(store_id, status)
        return [OwnerQuestionView(question, name) for question, name in rows]

    async def answer(
        self,
        store_id: UUID,
        question_id: UUID,
        user_id: UUID,
        text: str,
        add_to_manual: bool,
    ) -> OwnerQuestionView:
        """사장님 답변을 저장하고 알바생 채팅에 전달합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        if add_to_manual:
            raise AddToManualNotSupportedError
        row = await self._repository.get_by_id_and_store_id(question_id, store_id)
        if row is None:
            raise OwnerQuestionNotFoundError
        question, staff_name = row
        if question.status == OWNER_QUESTION_ANSWERED:
            raise OwnerQuestionAlreadyAnsweredError
        chat = await self._repository.get_chat(question.chat_id)
        if chat is None:
            raise OwnerQuestionNotFoundError

        answered_at = _after(chat.last_message_at)
        owner_message = AssistantMessage(
            chat_id=chat.id,
            sender="owner",
            text=text,
            sources=[],
            created_at=answered_at,
        )
        chat.last_message_at = answered_at
        chat.last_message_text = text
        saved = await self._repository.save_answer(
            question,
            user_id,
            answered_at,
            owner_message,
            chat,
        )
        if not saved:
            raise OwnerQuestionAlreadyAnsweredError
        return OwnerQuestionView(question, staff_name)
