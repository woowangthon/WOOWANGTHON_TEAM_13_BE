import json
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.integrations.llm import LLMError
from app.models.assistant_chat import AssistantChat, AssistantMessage
from app.models.manual import Manual
from app.models.recipe import Recipe
from app.services.assistant_chat import (
    HISTORY_LIMIT,
    HISTORY_TEXT_MAX_LENGTH,
    NOT_FOUND_TEXT,
    OUT_OF_SCOPE_TEXT,
    AssistantChatNotFoundError,
    AssistantChatService,
    AssistantDocument,
    AssistantMessageNotFoundError,
    build_history,
    interpret_answer,
)
from app.services.store import StoreNotFoundError

STORE_ID = uuid4()
USER_ID = uuid4()


class FakeChatRepository:
    def __init__(self) -> None:
        self.chats: list[AssistantChat] = []
        self.messages: list[AssistantMessage] = []
        self.events: list[str] = []

    async def release(self) -> None:
        self.events.append("release")

    async def save_chat(self, chat: AssistantChat) -> AssistantChat:
        if chat.id is None:
            chat.id = uuid4()
            self.chats.append(chat)
        return chat

    async def list_chats(self, store_id: UUID, user_id: UUID) -> list[AssistantChat]:
        return [
            chat
            for chat in self.chats
            if chat.store_id == store_id
            and chat.user_id == user_id
            and chat.deleted_at is None
        ]

    async def get_chat(
        self,
        chat_id: UUID,
        store_id: UUID,
        user_id: UUID,
    ) -> AssistantChat | None:
        chats = await self.list_chats(store_id, user_id)
        return next((chat for chat in chats if chat.id == chat_id), None)

    async def get_message(
        self,
        message_id: UUID,
        chat_id: UUID,
    ) -> AssistantMessage | None:
        return next(
            (
                message
                for message in self.messages
                if message.id == message_id and message.chat_id == chat_id
            ),
            None,
        )

    async def list_messages(
        self,
        chat_id: UUID,
        before: AssistantMessage | None,
        limit: int,
    ) -> list[AssistantMessage]:
        messages = [
            message
            for message in self.messages
            if message.chat_id == chat_id
            and (before is None or message.created_at < before.created_at)
        ]
        messages.sort(key=lambda message: message.created_at, reverse=True)
        return messages[:limit]

    async def save_exchange(
        self,
        chat: AssistantChat,
        question: AssistantMessage,
        answer: AssistantMessage,
    ) -> None:
        self.events.append("save")
        self.messages.extend([question, answer])


class FakeDocuments:
    def __init__(self, items: list[Any]) -> None:
        self.items = items
        self.store_ids: list[UUID] = []

    async def list_by_store_id(self, store_id: UUID) -> list[Any]:
        self.store_ids.append(store_id)
        return self.items


class FakeStoreAccess:
    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        await self.ensure_member(store_id, user_id)

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        if store_id != STORE_ID or user_id != USER_ID:
            raise StoreNotFoundError


class FakeLLM:
    def __init__(self, repository: FakeChatRepository) -> None:
        self.repository = repository
        self.result: Mapping[str, Any] = {}
        self.error: Exception | None = None
        self.prompts: list[str] = []

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.repository.events.append("llm")
        self.prompts.append(user_prompt)
        if self.error is not None:
            raise self.error
        return self.result


MANUAL = Manual(id=uuid4(), store_id=STORE_ID, title="와이파이", body="moon2026")
RECIPE = Recipe(
    id=uuid4(),
    store_id=STORE_ID,
    name="딸기라떼",
    category="라떼",
    temp="ICE",
    size="16oz",
    ingredients=[{"name": "딸기청", "amount": "3스푼"}],
    steps=["딸기청을 넣어요"],
    memo=None,
)


class Harness:
    def __init__(self, with_documents: bool = True) -> None:
        self.repository = FakeChatRepository()
        self.llm = FakeLLM(self.repository)
        self.manuals = FakeDocuments([MANUAL] if with_documents else [])
        self.recipes = FakeDocuments([RECIPE] if with_documents else [])
        self.service = AssistantChatService(
            self.repository,
            self.manuals,
            self.recipes,
            FakeStoreAccess(),
            self.llm,
        )

    async def chat(self) -> AssistantChat:
        chat, _ = await self.service.create_chat(STORE_ID, USER_ID)
        return chat


@pytest.fixture
def harness() -> Harness:
    return Harness()


DOCUMENTS = [
    AssistantDocument("manual", MANUAL.id, "와이파이", {"body": "moon2026"}),
    AssistantDocument("recipe", RECIPE.id, "딸기라떼", {"steps": []}),
]


def test_interpret_answer_builds_sources_from_real_documents() -> None:
    answer = interpret_answer(
        {
            "answerType": "answered",
            "text": " 3스푼이에요 ",
            "sourceIds": [str(RECIPE.id), str(RECIPE.id)],
        },
        DOCUMENTS,
    )

    assert answer.answer_type == "answered"
    assert answer.text == "3스푼이에요"
    assert answer.sources == [
        {"kind": "recipe", "id": str(RECIPE.id), "title": "딸기라떼"}
    ]


@pytest.mark.parametrize(
    "result",
    [
        {"answerType": "answered", "text": "지어낸 답", "sourceIds": []},
        {"answerType": "answered", "text": "지어낸 답", "sourceIds": [str(uuid4())]},
        {"answerType": "answered", "text": "지어낸 답", "sourceIds": "wrong"},
        {"answerType": "answered", "text": "  ", "sourceIds": [str(MANUAL.id)]},
        {"answerType": "not_found", "text": "지어낸 답", "sourceIds": [str(MANUAL.id)]},
    ],
)
def test_ungrounded_answer_becomes_fixed_not_found(
    result: Mapping[str, Any],
) -> None:
    answer = interpret_answer(result, DOCUMENTS)

    assert answer.answer_type == "not_found"
    assert answer.text == NOT_FOUND_TEXT
    assert answer.sources == []


def test_out_of_scope_uses_fixed_text() -> None:
    answer = interpret_answer(
        {"answerType": "out_of_scope", "text": "날씨는 맑아요", "sourceIds": []},
        DOCUMENTS,
    )

    assert answer.text == OUT_OF_SCOPE_TEXT
    assert answer.sources == []


def test_unknown_answer_type_raises_llm_error() -> None:
    with pytest.raises(LLMError):
        interpret_answer({"answerType": "maybe"}, DOCUMENTS)


async def test_send_message_saves_grounded_exchange(harness: Harness) -> None:
    chat = await harness.chat()
    harness.llm.result = {
        "answerType": "answered",
        "text": "moon2026이에요",
        "sourceIds": [str(MANUAL.id)],
    }

    question, answer = await harness.service.send_message(
        STORE_ID,
        chat.id,
        USER_ID,
        "와이파이 비번 뭐야?",
    )

    assert question.sender == "staff"
    assert answer.sender == "ai"
    assert answer.sources[0]["title"] == "와이파이"
    assert question.created_at <= answer.created_at
    assert chat.last_message_text == "moon2026이에요"
    assert harness.repository.messages == [question, answer]


async def test_prompt_contains_question_and_only_current_store_documents(
    harness: Harness,
) -> None:
    chat = await harness.chat()
    harness.llm.result = {"answerType": "not_found", "text": "", "sourceIds": []}

    await harness.service.send_message(STORE_ID, chat.id, USER_ID, "질문")

    prompt = json.loads(harness.llm.prompts[0])
    assert prompt["question"] == "질문"
    assert {item["title"] for item in prompt["documents"]} == {"와이파이", "딸기라떼"}
    assert set(harness.manuals.store_ids) == {STORE_ID}
    assert set(harness.recipes.store_ids) == {STORE_ID}


async def test_transaction_is_released_before_llm_call(harness: Harness) -> None:
    chat = await harness.chat()
    harness.llm.result = {"answerType": "not_found", "text": "", "sourceIds": []}

    await harness.service.send_message(STORE_ID, chat.id, USER_ID, "질문")

    assert harness.repository.events == ["release", "llm", "save"]


async def test_no_documents_skips_llm() -> None:
    harness = Harness(with_documents=False)
    chat = await harness.chat()

    _, answer = await harness.service.send_message(STORE_ID, chat.id, USER_ID, "질문")

    assert answer.answer_type == "not_found"
    assert harness.llm.prompts == []


async def test_llm_failure_saves_nothing(harness: Harness) -> None:
    chat = await harness.chat()
    harness.llm.error = LLMError()

    with pytest.raises(LLMError):
        await harness.service.send_message(STORE_ID, chat.id, USER_ID, "질문")

    assert harness.repository.messages == []


async def test_other_users_chat_is_not_found(harness: Harness) -> None:
    chat = AssistantChat(
        id=uuid4(),
        store_id=STORE_ID,
        user_id=uuid4(),
        last_message_at=datetime.now(UTC),
    )
    harness.repository.chats.append(chat)

    with pytest.raises(AssistantChatNotFoundError):
        await harness.service.send_message(STORE_ID, chat.id, USER_ID, "질문")
    with pytest.raises(AssistantChatNotFoundError):
        await harness.service.list_messages(STORE_ID, chat.id, USER_ID, None, 50)
    with pytest.raises(AssistantChatNotFoundError):
        await harness.service.delete_chat(STORE_ID, chat.id, USER_ID)


async def test_stranger_cannot_create_chat(harness: Harness) -> None:
    with pytest.raises(StoreNotFoundError):
        await harness.service.create_chat(STORE_ID, uuid4())


async def test_deleted_chat_is_hidden(harness: Harness) -> None:
    chat = await harness.chat()

    await harness.service.delete_chat(STORE_ID, chat.id, USER_ID)

    chats, _ = await harness.service.list_chats(STORE_ID, USER_ID)
    assert chats == []


async def test_suggestions_come_from_manual_titles(harness: Harness) -> None:
    _, suggestions = await harness.service.create_chat(STORE_ID, USER_ID)

    assert suggestions == ["와이파이"]


def add_messages(harness: Harness, chat: AssistantChat, count: int) -> None:
    start = datetime.now(UTC)
    for index in range(count):
        harness.repository.messages.append(
            AssistantMessage(
                id=uuid4(),
                chat_id=chat.id,
                sender="staff",
                text=str(index),
                sources=[],
                created_at=start + timedelta(seconds=index),
            )
        )


async def test_list_messages_returns_oldest_first_with_has_more(
    harness: Harness,
) -> None:
    chat = await harness.chat()
    add_messages(harness, chat, 3)

    messages, has_more = await harness.service.list_messages(
        STORE_ID,
        chat.id,
        USER_ID,
        None,
        2,
    )

    assert [message.text for message in messages] == ["1", "2"]
    assert has_more is True


async def test_list_messages_before_cursor(harness: Harness) -> None:
    chat = await harness.chat()
    add_messages(harness, chat, 3)
    cursor = harness.repository.messages[2]

    messages, has_more = await harness.service.list_messages(
        STORE_ID,
        chat.id,
        USER_ID,
        cursor.id,
        50,
    )

    assert [message.text for message in messages] == ["0", "1"]
    assert has_more is False


async def test_unknown_cursor_is_not_found(harness: Harness) -> None:
    chat = await harness.chat()

    with pytest.raises(AssistantMessageNotFoundError):
        await harness.service.list_messages(STORE_ID, chat.id, USER_ID, uuid4(), 50)


def history_message(
    chat: AssistantChat,
    sender: str,
    text: str,
    seconds: int,
) -> AssistantMessage:
    return AssistantMessage(
        id=uuid4(),
        chat_id=chat.id,
        sender=sender,
        text=text,
        answer_type=None,
        sources=[],
        created_at=datetime(2026, 11, 8, tzinfo=UTC) + timedelta(seconds=seconds),
    )


async def test_prompt_includes_recent_history_oldest_first(harness: Harness) -> None:
    chat = await harness.chat()
    harness.repository.messages.extend(
        [
            history_message(chat, "staff", "딸기라떼 레시피 알려줘", 1),
            history_message(chat, "ai", "딸기청 3스푼이에요", 2),
            history_message(chat, "system", "사장님께 전달했어요", 3),
            history_message(chat, "owner", "우산은 빌려주세요", 4),
        ]
    )
    harness.llm.result = {"answerType": "not_found", "text": "", "sourceIds": []}

    await harness.service.send_message(STORE_ID, chat.id, USER_ID, "그럼 따뜻한 건?")

    prompt = json.loads(harness.llm.prompts[0])
    assert prompt["question"] == "그럼 따뜻한 건?"
    assert prompt["history"] == [
        {"role": "staff", "text": "딸기라떼 레시피 알려줘"},
        {"role": "assistant", "text": "딸기청 3스푼이에요"},
        {"role": "owner", "text": "우산은 빌려주세요"},
    ]


async def test_history_is_limited_to_recent_messages(harness: Harness) -> None:
    chat = await harness.chat()
    harness.repository.messages.extend(
        history_message(chat, "staff", f"질문 {index}", index) for index in range(10)
    )
    harness.llm.result = {"answerType": "not_found", "text": "", "sourceIds": []}

    await harness.service.send_message(STORE_ID, chat.id, USER_ID, "새 질문")

    history = json.loads(harness.llm.prompts[0])["history"]
    assert [item["text"] for item in history] == [
        f"질문 {index}" for index in range(10 - HISTORY_LIMIT, 10)
    ]


async def test_history_excludes_other_chats(harness: Harness) -> None:
    chat = await harness.chat()
    other = await harness.chat()
    harness.repository.messages.append(history_message(other, "staff", "다른 방", 1))
    harness.llm.result = {"answerType": "not_found", "text": "", "sourceIds": []}

    await harness.service.send_message(STORE_ID, chat.id, USER_ID, "질문")

    assert json.loads(harness.llm.prompts[0])["history"] == []


def test_build_history_truncates_long_text() -> None:
    chat = AssistantChat(id=uuid4())
    message = history_message(chat, "staff", "가" * 500, 0)

    history = build_history([message])

    assert history == [{"role": "staff", "text": "가" * HISTORY_TEXT_MAX_LENGTH}]
