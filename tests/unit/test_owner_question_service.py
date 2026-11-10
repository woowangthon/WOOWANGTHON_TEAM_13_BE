from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

import pytest

from app.models.assistant_chat import AssistantChat, AssistantMessage
from app.models.manual import Manual, ManualCategory
from app.models.owner_question import OwnerQuestion
from app.services.assistant_chat import (
    AssistantChatNotFoundError,
    AssistantMessageNotFoundError,
)
from app.services.manual import ManualCategoryNotFoundError
from app.services.owner_question import (
    ASKED_SYSTEM_TEXT,
    DEFAULT_MANUAL_CATEGORY,
    ManualDraft,
    OwnerQuestionAlreadyAnsweredError,
    OwnerQuestionAlreadySentError,
    OwnerQuestionNotAllowedError,
    OwnerQuestionNotFoundError,
    OwnerQuestionService,
    question_title,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError

STORE_ID = uuid4()
OWNER_ID = uuid4()
STAFF_ID = uuid4()
OTHER_STAFF_ID = uuid4()
NOW = datetime(2026, 11, 8, 10, tzinfo=UTC)


class FakeStoreAccess:
    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        if store_id != STORE_ID:
            raise StoreNotFoundError
        if user_id in (STAFF_ID, OTHER_STAFF_ID):
            raise StoreAccessForbiddenError
        if user_id != OWNER_ID:
            raise StoreNotFoundError

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        if store_id != STORE_ID or user_id not in (OWNER_ID, STAFF_ID, OTHER_STAFF_ID):
            raise StoreNotFoundError


class FakeChats:
    def __init__(self) -> None:
        self.chats: list[AssistantChat] = []
        self.messages: list[AssistantMessage] = []

    async def get_chat(
        self,
        chat_id: UUID,
        store_id: UUID,
        user_id: UUID,
    ) -> AssistantChat | None:
        for chat in self.chats:
            if (chat.id, chat.store_id, chat.user_id) == (chat_id, store_id, user_id):
                return chat
        return None

    async def get_message(
        self,
        message_id: UUID,
        chat_id: UUID,
    ) -> AssistantMessage | None:
        for message in self.messages:
            if message.id == message_id and message.chat_id == chat_id:
                return message
        return None

    async def get_previous_staff_message(
        self,
        message: AssistantMessage,
    ) -> AssistantMessage | None:
        earlier = [
            item
            for item in self.messages
            if item.chat_id == message.chat_id
            and item.sender == "staff"
            and item.created_at <= message.created_at
            and item.id != message.id
        ]
        return max(earlier, key=lambda item: item.created_at, default=None)


class FakeCategories:
    def __init__(self) -> None:
        self.categories: list[ManualCategory] = []

    async def get_category(
        self,
        category_id: UUID,
        store_id: UUID,
    ) -> ManualCategory | None:
        for category in self.categories:
            if category.id == category_id and category.store_id == store_id:
                return category
        return None

    async def get_category_by_name(
        self,
        store_id: UUID,
        name: str,
    ) -> ManualCategory | None:
        for category in self.categories:
            if category.store_id == store_id and category.name == name:
                return category
        return None


class FakeOwnerQuestions:
    def __init__(self, chats: FakeChats) -> None:
        self.chats = chats
        self.questions: list[OwnerQuestion] = []
        self.saved_messages: list[AssistantMessage] = []
        self.saved_manuals: list[Manual] = []
        self.saved_categories: list[ManualCategory] = []
        self.race_on_ask = False
        self.race_on_answer = False

    async def list_by_message_ids(
        self,
        message_ids: list[UUID],
    ) -> list[OwnerQuestion]:
        return [item for item in self.questions if item.message_id in message_ids]

    async def list_by_store_id(
        self,
        store_id: UUID,
        status: str | None,
    ) -> list[tuple[OwnerQuestion, str]]:
        return [
            (item, "지은")
            for item in self.questions
            if item.store_id == store_id and status in (None, item.status)
        ]

    async def get_by_id_and_store_id(
        self,
        question_id: UUID,
        store_id: UUID,
    ) -> tuple[OwnerQuestion, str] | None:
        for item in self.questions:
            if item.id == question_id and item.store_id == store_id:
                return item, "지은"
        return None

    async def get_chat(self, chat_id: UUID) -> AssistantChat | None:
        return next((chat for chat in self.chats.chats if chat.id == chat_id), None)

    async def save_asked(
        self,
        question: OwnerQuestion,
        system_message: AssistantMessage,
        chat: AssistantChat,
    ) -> bool:
        if self.race_on_ask:
            return False
        question.id = uuid4()
        self.questions.append(question)
        self.saved_messages.append(system_message)
        return True

    async def save_answer(
        self,
        question: OwnerQuestion,
        answered_by: UUID,
        answered_at: datetime,
        owner_message: AssistantMessage,
        chat: AssistantChat,
        manual: Manual | None = None,
        category: ManualCategory | None = None,
    ) -> bool:
        if self.race_on_answer:
            return False
        if category is not None:
            self.saved_categories.append(category)
        if manual is not None:
            self.saved_manuals.append(manual)
        question.status = "answered"
        question.answer = owner_message.text
        question.answered_by = answered_by
        question.answered_at = answered_at
        self.saved_messages.append(owner_message)
        return True


class Harness:
    def __init__(self) -> None:
        self.chats = FakeChats()
        self.repository = FakeOwnerQuestions(self.chats)
        self.categories = FakeCategories()
        self.service = OwnerQuestionService(
            self.chats,
            self.repository,
            FakeStoreAccess(),
            self.categories,
        )
        self.chat = AssistantChat(
            id=uuid4(),
            store_id=STORE_ID,
            user_id=STAFF_ID,
            last_message_at=NOW,
            last_message_text=None,
        )
        self.chats.chats.append(self.chat)

    def add_message(
        self,
        sender: str,
        text: str,
        answer_type: str | None = None,
        offset: int = 0,
    ) -> AssistantMessage:
        message = AssistantMessage(
            id=uuid4(),
            chat_id=self.chat.id,
            sender=sender,
            text=text,
            answer_type=answer_type,
            sources=[],
            created_at=NOW + timedelta(seconds=offset),
        )
        self.chats.messages.append(message)
        return message

    def not_found_exchange(
        self, question: str = "우산 빌려줘도 돼요?"
    ) -> AssistantMessage:
        self.add_message("staff", "와이파이 비번?", offset=-10)
        self.add_message("ai", "moon2026이에요", "answered", offset=-9)
        self.add_message("staff", question)
        return self.add_message("ai", "매뉴얼에서 찾지 못했어요.", "not_found")

    async def ask(self, answer: AssistantMessage) -> OwnerQuestion:
        question, _ = await self.service.ask(
            STORE_ID, self.chat.id, answer.id, STAFF_ID
        )
        return question


@pytest.fixture
def harness() -> Harness:
    return Harness()


async def test_ask_saves_original_question_and_system_message(
    harness: Harness,
) -> None:
    answer = harness.not_found_exchange()

    question, system_message = await harness.service.ask(
        STORE_ID,
        harness.chat.id,
        answer.id,
        STAFF_ID,
    )

    assert question.question == "우산 빌려줘도 돼요?"
    assert question.status == "asked"
    assert question.message_id == answer.id
    assert question.asked_by == STAFF_ID
    assert system_message.sender == "system"
    assert system_message.text == ASKED_SYSTEM_TEXT
    assert system_message.created_at > answer.created_at
    assert harness.chat.last_message_text == ASKED_SYSTEM_TEXT


@pytest.mark.parametrize(
    ("sender", "answer_type"),
    [("ai", "answered"), ("ai", "out_of_scope"), ("staff", None)],
)
async def test_only_not_found_answer_can_be_asked(
    harness: Harness,
    sender: str,
    answer_type: str | None,
) -> None:
    harness.add_message("staff", "질문", offset=-1)
    message = harness.add_message(sender, "답", answer_type)

    with pytest.raises(OwnerQuestionNotAllowedError):
        await harness.ask(message)


async def test_same_answer_cannot_be_asked_twice(harness: Harness) -> None:
    answer = harness.not_found_exchange()
    await harness.ask(answer)

    with pytest.raises(OwnerQuestionAlreadySentError):
        await harness.ask(answer)


async def test_concurrent_duplicate_ask_is_conflict(harness: Harness) -> None:
    answer = harness.not_found_exchange()
    harness.repository.race_on_ask = True

    with pytest.raises(OwnerQuestionAlreadySentError):
        await harness.ask(answer)


async def test_other_users_chat_is_not_found(harness: Harness) -> None:
    answer = harness.not_found_exchange()

    with pytest.raises(AssistantChatNotFoundError):
        await harness.service.ask(
            STORE_ID,
            harness.chat.id,
            answer.id,
            OTHER_STAFF_ID,
        )


async def test_message_from_another_chat_is_not_found(harness: Harness) -> None:
    harness.not_found_exchange()

    with pytest.raises(AssistantMessageNotFoundError):
        await harness.service.ask(STORE_ID, harness.chat.id, uuid4(), STAFF_ID)


async def test_stranger_cannot_ask(harness: Harness) -> None:
    answer = harness.not_found_exchange()

    with pytest.raises(StoreNotFoundError):
        await harness.service.ask(STORE_ID, harness.chat.id, answer.id, uuid4())


async def test_questions_for_messages_maps_only_ai_answers(harness: Harness) -> None:
    answer = harness.not_found_exchange()
    question = await harness.ask(answer)

    mapped = await harness.service.questions_for_messages(harness.chats.messages)

    assert mapped == {answer.id: question}


async def test_staff_cannot_list_questions(harness: Harness) -> None:
    with pytest.raises(StoreAccessForbiddenError):
        await harness.service.list_questions(STORE_ID, STAFF_ID, None)


async def test_owner_lists_questions_by_status(harness: Harness) -> None:
    question = await harness.ask(harness.not_found_exchange())

    asked = await harness.service.list_questions(STORE_ID, OWNER_ID, "asked")
    answered = await harness.service.list_questions(STORE_ID, OWNER_ID, "answered")

    assert [view.question for view in asked] == [question]
    assert answered == []


async def test_owner_answer_is_delivered_to_staff_chat(harness: Harness) -> None:
    question = await harness.ask(harness.not_found_exchange())

    view = await harness.service.answer(
        STORE_ID,
        question.id,
        OWNER_ID,
        "카운터 아래 우산 빌려주세요",
    )

    assert view.question.status == "answered"
    assert view.question.answer == "카운터 아래 우산 빌려주세요"
    assert view.question.answered_by == OWNER_ID
    owner_message = harness.repository.saved_messages[-1]
    assert owner_message.sender == "owner"
    assert owner_message.chat_id == harness.chat.id
    assert owner_message.created_at > NOW
    assert harness.chat.last_message_text == "카운터 아래 우산 빌려주세요"


async def test_answered_question_cannot_be_answered_again(harness: Harness) -> None:
    question = await harness.ask(harness.not_found_exchange())
    await harness.service.answer(STORE_ID, question.id, OWNER_ID, "답변")

    with pytest.raises(OwnerQuestionAlreadyAnsweredError):
        await harness.service.answer(STORE_ID, question.id, OWNER_ID, "또")


async def test_concurrent_answer_is_conflict(harness: Harness) -> None:
    question = await harness.ask(harness.not_found_exchange())
    harness.repository.race_on_answer = True

    with pytest.raises(OwnerQuestionAlreadyAnsweredError):
        await harness.service.answer(STORE_ID, question.id, OWNER_ID, "답변")


async def test_answer_without_manual_saves_no_manual(harness: Harness) -> None:
    question = await harness.ask(harness.not_found_exchange())

    view = await harness.service.answer(STORE_ID, question.id, OWNER_ID, "답변")

    assert view.manual_id is None
    assert harness.repository.saved_manuals == []


async def test_add_to_manual_uses_question_and_default_category(
    harness: Harness,
) -> None:
    question = await harness.ask(harness.not_found_exchange("쓰레받기 어딨어?"))

    view = await harness.service.answer(
        STORE_ID,
        question.id,
        OWNER_ID,
        "창고 왼쪽 선반에 빗자루, 쓰레받기가 있어요",
        ManualDraft(),
    )

    [manual] = harness.repository.saved_manuals
    [category] = harness.repository.saved_categories
    assert view.manual_id == manual.id
    assert manual.store_id == STORE_ID
    assert manual.title == "쓰레받기 어딨어?"
    assert manual.body == (
        "질문: 쓰레받기 어딨어?\n답변: 창고 왼쪽 선반에 빗자루, 쓰레받기가 있어요"
    )
    assert manual.icon is None
    assert category.name == DEFAULT_MANUAL_CATEGORY
    assert category.store_id == STORE_ID
    assert manual.category_id == category.id
    assert question.status == "answered"


async def test_add_to_manual_reuses_existing_default_category(
    harness: Harness,
) -> None:
    existing = ManualCategory(id=uuid4(), store_id=STORE_ID, name="물건 위치")
    harness.categories.categories.append(existing)
    question = await harness.ask(harness.not_found_exchange())

    await harness.service.answer(STORE_ID, question.id, OWNER_ID, "답", ManualDraft())

    [manual] = harness.repository.saved_manuals
    assert manual.category_id == existing.id
    assert harness.repository.saved_categories == []


async def test_add_to_manual_uses_owner_edits(harness: Harness) -> None:
    chosen = ManualCategory(id=uuid4(), store_id=STORE_ID, name="오픈")
    harness.categories.categories.append(chosen)
    question = await harness.ask(harness.not_found_exchange())
    draft = ManualDraft(
        title="우산 대여",
        body="카운터 아래 우산",
        category_id=chosen.id,
    )

    await harness.service.answer(STORE_ID, question.id, OWNER_ID, "네", draft)

    [manual] = harness.repository.saved_manuals
    assert (manual.title, manual.body, manual.category_id) == (
        "우산 대여",
        "카운터 아래 우산",
        chosen.id,
    )
    assert harness.repository.saved_categories == []


async def test_add_to_manual_rejects_other_store_category(harness: Harness) -> None:
    other = ManualCategory(id=uuid4(), store_id=uuid4(), name="물건 위치")
    harness.categories.categories.append(other)
    question = await harness.ask(harness.not_found_exchange())

    with pytest.raises(ManualCategoryNotFoundError):
        await harness.service.answer(
            STORE_ID,
            question.id,
            OWNER_ID,
            "답",
            ManualDraft(category_id=other.id),
        )
    assert question.status == "asked"
    assert harness.repository.saved_manuals == []


async def test_concurrent_answer_with_manual_saves_nothing(harness: Harness) -> None:
    question = await harness.ask(harness.not_found_exchange())
    harness.repository.race_on_answer = True

    with pytest.raises(OwnerQuestionAlreadyAnsweredError):
        await harness.service.answer(
            STORE_ID, question.id, OWNER_ID, "답", ManualDraft()
        )
    assert harness.repository.saved_manuals == []


async def test_staff_cannot_answer(harness: Harness) -> None:
    question = await harness.ask(harness.not_found_exchange())

    with pytest.raises(StoreAccessForbiddenError):
        await harness.service.answer(STORE_ID, question.id, STAFF_ID, "답변")


async def test_unknown_question_is_not_found(harness: Harness) -> None:
    with pytest.raises(OwnerQuestionNotFoundError):
        await harness.service.answer(STORE_ID, uuid4(), OWNER_ID, "답변")


def test_question_title_uses_leading_text() -> None:
    assert question_title("  우산   빌려줘도 돼요? ") == "우산 빌려줘도 돼요?"
    long_title = question_title("가" * 40)
    assert long_title == "가" * 30 + "…"
