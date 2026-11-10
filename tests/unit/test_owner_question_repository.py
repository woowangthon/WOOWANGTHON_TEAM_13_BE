from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.assistant_chat import AssistantChat, AssistantMessage
from app.models.manual import Manual, ManualCategory
from app.models.membership import Membership
from app.models.owner_question import OwnerQuestion
from app.models.store import Store
from app.models.user import User
from app.repositories.assistant_chat import AssistantChatRepository
from app.repositories.owner_question import OwnerQuestionRepository

NOW = datetime(2026, 11, 8, 10, tzinfo=UTC)


@compiles(JSONB, "sqlite")
def _jsonb_as_json(_type: Any, _compiler: Any, **_kw: Any) -> str:
    return "JSON"


class SyncSessionAdapter:
    """실제 쿼리를 SQLite에서 실행하도록 동기 세션을 감쌉니다."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, query: Any) -> Any:
        return self._session.execute(query)

    async def get(self, model: Any, key: Any) -> Any:
        return self._session.get(model, key)

    def add(self, item: Any) -> None:
        self._session.add(item)

    def add_all(self, items: list[Any]) -> None:
        self._session.add_all(items)

    async def flush(self) -> None:
        self._session.flush()

    async def commit(self) -> None:
        self._session.commit()

    async def rollback(self) -> None:
        self._session.rollback()

    async def refresh(self, item: Any) -> None:
        self._session.refresh(item)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    tables = [
        User.__table__,
        Store.__table__,
        Membership.__table__,
        AssistantChat.__table__,
        AssistantMessage.__table__,
        OwnerQuestion.__table__,
        ManualCategory.__table__,
        Manual.__table__,
    ]
    User.metadata.create_all(engine, tables=tables)
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session
    engine.dispose()


def as_async(session: Session) -> AsyncSession:
    return cast(AsyncSession, SyncSessionAdapter(session))


def add_user(session: Session, nickname: str) -> UUID:
    user = User(id=uuid4(), auth_user_id=uuid4(), nickname=nickname, provider="kakao")
    session.add(user)
    return user.id


def add_store(session: Session) -> UUID:
    store = Store(id=uuid4(), owner_id=uuid4(), name="매장", address="주소")
    session.add(store)
    return store.id


def add_chat(session: Session, store_id: UUID, user_id: UUID) -> AssistantChat:
    chat = AssistantChat(
        id=uuid4(),
        store_id=store_id,
        user_id=user_id,
        last_message_at=NOW,
    )
    session.add(chat)
    return chat


def add_message(
    session: Session,
    chat: AssistantChat,
    sender: str,
    text: str,
    seconds: int,
) -> AssistantMessage:
    message = AssistantMessage(
        id=uuid4(),
        chat_id=chat.id,
        sender=sender,
        text=text,
        answer_type="not_found" if sender == "ai" else None,
        sources=[],
        created_at=NOW + timedelta(seconds=seconds),
    )
    session.add(message)
    return message


def add_question(
    session: Session,
    chat: AssistantChat,
    message: AssistantMessage,
    asked_by: UUID,
    status: str = "asked",
    seconds: int = 0,
) -> OwnerQuestion:
    question = OwnerQuestion(
        id=uuid4(),
        store_id=chat.store_id,
        chat_id=chat.id,
        message_id=message.id,
        asked_by=asked_by,
        question="우산 빌려줘도 돼요?",
        status=status,
        created_at=NOW + timedelta(seconds=seconds),
    )
    session.add(question)
    return question


def add_membership(session: Session, store_id: UUID, user_id: UUID) -> None:
    session.add(
        Membership(
            store_id=store_id,
            user_id=user_id,
            role="staff",
            staff_name="지은",
            hourly_wage=10320,
            joined_at=NOW,
        )
    )


async def test_lists_store_questions_with_staff_name(session: Session) -> None:
    store_id = add_store(session)
    staff_id = add_user(session, "카카오닉네임")
    owner_id = add_user(session, "사장님닉네임")
    add_membership(session, store_id, staff_id)
    staff_chat = add_chat(session, store_id, staff_id)
    owner_chat = add_chat(session, store_id, owner_id)
    first = add_question(
        session,
        staff_chat,
        add_message(session, staff_chat, "ai", "답", 1),
        staff_id,
    )
    second = add_question(
        session,
        owner_chat,
        add_message(session, owner_chat, "ai", "답", 2),
        owner_id,
        seconds=5,
    )
    other_store = add_store(session)
    other_chat = add_chat(session, other_store, staff_id)
    add_question(
        session,
        other_chat,
        add_message(session, other_chat, "ai", "답", 3),
        staff_id,
    )
    session.commit()

    rows = await OwnerQuestionRepository(as_async(session)).list_by_store_id(
        store_id,
        None,
    )

    assert [(question.id, name) for question, name in rows] == [
        (second.id, "사장님닉네임"),
        (first.id, "지은"),
    ]


async def test_filters_questions_by_status(session: Session) -> None:
    store_id = add_store(session)
    staff_id = add_user(session, "민지")
    chat = add_chat(session, store_id, staff_id)
    asked = add_question(
        session, chat, add_message(session, chat, "ai", "a", 1), staff_id
    )
    add_question(
        session,
        chat,
        add_message(session, chat, "ai", "b", 2),
        staff_id,
        status="answered",
    )
    session.commit()

    rows = await OwnerQuestionRepository(as_async(session)).list_by_store_id(
        store_id,
        "asked",
    )

    assert [question.id for question, _ in rows] == [asked.id]


async def test_get_question_is_limited_to_store(session: Session) -> None:
    store_id = add_store(session)
    staff_id = add_user(session, "민지")
    chat = add_chat(session, store_id, staff_id)
    question = add_question(
        session,
        chat,
        add_message(session, chat, "ai", "a", 1),
        staff_id,
    )
    session.commit()
    repository = OwnerQuestionRepository(as_async(session))

    assert await repository.get_by_id_and_store_id(question.id, store_id) is not None
    assert await repository.get_by_id_and_store_id(question.id, uuid4()) is None


async def test_duplicate_question_for_same_answer_returns_false(
    session: Session,
) -> None:
    store_id = add_store(session)
    staff_id = add_user(session, "민지")
    chat = add_chat(session, store_id, staff_id)
    answer = add_message(session, chat, "ai", "a", 1)
    add_question(session, chat, answer, staff_id)
    session.commit()
    duplicate = OwnerQuestion(
        id=uuid4(),
        store_id=store_id,
        chat_id=chat.id,
        message_id=answer.id,
        asked_by=staff_id,
        question="중복",
        status="asked",
        created_at=NOW,
    )
    system_message = AssistantMessage(
        id=uuid4(),
        chat_id=chat.id,
        sender="system",
        text="사장님께 전달했어요",
        sources=[],
        created_at=NOW,
    )

    saved = await OwnerQuestionRepository(as_async(session)).save_asked(
        duplicate,
        system_message,
        chat,
    )

    assert saved is False
    assert session.get(AssistantMessage, system_message.id) is None


async def test_save_answer_updates_only_unanswered_question(
    session: Session,
) -> None:
    store_id = add_store(session)
    staff_id = add_user(session, "민지")
    owner_id = add_user(session, "사장님")
    chat = add_chat(session, store_id, staff_id)
    question = add_question(
        session,
        chat,
        add_message(session, chat, "ai", "a", 1),
        staff_id,
    )
    session.commit()
    repository = OwnerQuestionRepository(as_async(session))

    def owner_message(text: str) -> AssistantMessage:
        return AssistantMessage(
            id=uuid4(),
            chat_id=chat.id,
            sender="owner",
            text=text,
            sources=[],
            created_at=NOW + timedelta(seconds=9),
        )

    first = owner_message("카운터 아래 우산")
    second = owner_message("두 번째 답변")
    answered_at = NOW + timedelta(seconds=9)

    assert await repository.save_answer(question, owner_id, answered_at, first, chat)
    assert not await repository.save_answer(
        question,
        owner_id,
        answered_at,
        second,
        chat,
    )
    assert question.status == "answered"
    assert question.answer == "카운터 아래 우산"
    assert question.answered_by == owner_id
    assert session.get(AssistantMessage, first.id) is not None
    assert session.get(AssistantMessage, second.id) is None


async def test_save_answer_with_manual_commits_together(session: Session) -> None:
    store_id = add_store(session)
    staff_id = add_user(session, "민지")
    owner_id = add_user(session, "사장님")
    chat = add_chat(session, store_id, staff_id)
    question = add_question(
        session,
        chat,
        add_message(session, chat, "ai", "a", 1),
        staff_id,
    )
    session.commit()
    repository = OwnerQuestionRepository(as_async(session))

    def answer_parts(text: str) -> tuple[AssistantMessage, ManualCategory, Manual]:
        category = ManualCategory(id=uuid4(), store_id=store_id, name="물건 위치")
        manual = Manual(
            id=uuid4(),
            store_id=store_id,
            category_id=category.id,
            title="우산",
            body=text,
        )
        message = AssistantMessage(
            id=uuid4(),
            chat_id=chat.id,
            sender="owner",
            text=text,
            sources=[],
            created_at=NOW + timedelta(seconds=9),
        )
        return message, category, manual

    first, first_category, first_manual = answer_parts("카운터 아래")
    second, second_category, second_manual = answer_parts("두 번째")
    answered_at = NOW + timedelta(seconds=9)

    assert await repository.save_answer(
        question, owner_id, answered_at, first, chat, first_manual, first_category
    )
    assert not await repository.save_answer(
        question, owner_id, answered_at, second, chat, second_manual, second_category
    )
    saved = session.get(Manual, first_manual.id)
    assert saved is not None
    assert saved.category_id == first_category.id
    assert session.get(ManualCategory, first_category.id) is not None
    assert session.get(Manual, second_manual.id) is None
    assert session.get(ManualCategory, second_category.id) is None


async def test_previous_staff_message_is_the_question_before_answer(
    session: Session,
) -> None:
    store_id = add_store(session)
    staff_id = add_user(session, "민지")
    chat = add_chat(session, store_id, staff_id)
    add_message(session, chat, "staff", "첫 질문", 0)
    add_message(session, chat, "ai", "첫 답", 1)
    add_message(session, chat, "staff", "우산 빌려줘도 돼요?", 2)
    answer = add_message(session, chat, "ai", "못 찾음", 2)
    add_message(session, chat, "staff", "나중 질문", 5)
    other_chat = add_chat(session, store_id, staff_id)
    add_message(session, other_chat, "staff", "다른 방 질문", 2)
    session.commit()

    found = await AssistantChatRepository(as_async(session)).get_previous_staff_message(
        answer
    )

    assert found is not None
    assert found.text == "우산 빌려줘도 돼요?"
