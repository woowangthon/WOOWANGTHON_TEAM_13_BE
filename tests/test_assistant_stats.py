from collections.abc import Iterator
from datetime import UTC, datetime, timedelta
from typing import Any, cast
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.ext.compiler import compiles
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.dependencies import get_active_user
from app.app import app
from app.db.session import get_db
from app.models.assistant_chat import AssistantChat, AssistantMessage
from app.models.membership import Membership
from app.models.store import Store
from app.models.user import User
from app.services import assistant_stats

# 2026-11-16 월요일 00:00 KST. DB 테스트 데이터는 UTC로 저장합니다.
START = datetime(2026, 11, 15, 15, tzinfo=UTC)


@compiles(JSONB, "sqlite")
def _jsonb_as_json(_type: Any, _compiler: Any, **_kw: Any) -> str:
    return "JSON"


class SyncSessionAdapter:
    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, query: Any) -> Any:
        return self._session.execute(query)


class StatsSetup:
    def __init__(self, session: Session) -> None:
        self.session = session
        self.owner = self.user("사장님")
        self.staff = self.user("닉네임")
        self.outsider = self.user("다른 매장 사장님")
        self.store = Store(
            id=uuid4(),
            owner_id=self.owner.id,
            name="매장",
            address="주소",
        )
        self.other_store = Store(
            id=uuid4(),
            owner_id=self.outsider.id,
            name="다른 매장",
            address="주소",
        )
        session.add_all([self.store, self.other_store])
        session.add(
            Membership(
                store_id=self.store.id,
                user_id=self.staff.id,
                staff_name="지은",
                hourly_wage=10320,
                role="staff",
            )
        )
        self.chat = self.new_chat(self.store, self.staff)
        self.current_user = self.owner
        self.client = TestClient(app)

    def user(self, nickname: str) -> User:
        user = User(
            id=uuid4(),
            auth_user_id=uuid4(),
            nickname=nickname,
            provider="kakao",
        )
        self.session.add(user)
        return user

    def new_chat(self, store: Store, user: User) -> AssistantChat:
        chat = AssistantChat(
            id=uuid4(),
            store_id=store.id,
            user_id=user.id,
            last_message_at=START,
        )
        self.session.add(chat)
        return chat

    def message(
        self,
        sender: str = "ai",
        answer_type: str | None = "answered",
        at: datetime = START,
        text: str = "메시지",
        chat: AssistantChat | None = None,
    ) -> AssistantMessage:
        message = AssistantMessage(
            id=uuid4(),
            chat_id=(chat or self.chat).id,
            sender=sender,
            answer_type=answer_type,
            created_at=at,
            text=text,
            sources=[],
        )
        self.session.add(message)
        return message

    def get(self, week: str | None = "2026-11-16") -> Any:
        self.session.commit()
        return self.client.get(
            f"/api/v1/stores/{self.store.id}/assistant-stats",
            params={"week": week} if week is not None else {},
        )


@pytest.fixture
def setup() -> Iterator[StatsSetup]:
    engine = create_engine(
        "sqlite://",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    User.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            Store.__table__,
            Membership.__table__,
            AssistantChat.__table__,
            AssistantMessage.__table__,
        ],
    )
    with Session(engine, expire_on_commit=False) as session:
        data = StatsSetup(session)
        app.dependency_overrides[get_db] = lambda: cast(
            AsyncSession,
            SyncSessionAdapter(session),
        )
        app.dependency_overrides[get_active_user] = lambda: data.current_user
        try:
            yield data
        finally:
            app.dependency_overrides.clear()
            data.client.close()
    engine.dispose()


def test_owner_response_shape_and_counts(setup: StatsSetup) -> None:
    setup.message(
        sender="staff",
        answer_type=None,
        at=START - timedelta(seconds=1),
        text="우유 스팀 온도 몇 도예요?",
    )
    unanswered = setup.message(answer_type="not_found")
    setup.message(at=START + timedelta(seconds=1))
    setup.message(at=START - timedelta(days=1))
    setup.message(answer_type="not_found", at=START - timedelta(days=2))

    response = setup.get()

    assert response.status_code == 200
    assert response.json() == {
        "weekStart": "2026-11-16",
        "total": 2,
        "answered": 1,
        "lastWeekRate": 50,
        "unanswered": [
            {
                "category": "기타",
                "questions": [
                    {
                        "questionId": str(unanswered.id),
                        "question": "우유 스팀 온도 몇 도예요?",
                        "staffName": "지은",
                    }
                ],
            }
        ],
    }


@pytest.mark.parametrize(("user", "status"), [("staff", 403), ("outsider", 404)])
def test_only_store_owner_can_read(setup: StatsSetup, user: str, status: int) -> None:
    setup.current_user = getattr(setup, user)
    assert setup.get().status_code == status


def test_deleted_store_returns_404(setup: StatsSetup) -> None:
    setup.store.deleted_at = START
    assert setup.get().status_code == 404


def test_empty_week(setup: StatsSetup) -> None:
    response = setup.get()
    assert response.status_code == 200
    assert response.json() == {
        "weekStart": "2026-11-16",
        "total": 0,
        "answered": 0,
        "lastWeekRate": None,
        "unanswered": [],
    }


def test_excludes_out_of_scope_non_ai_deleted_and_other_store(
    setup: StatsSetup,
) -> None:
    setup.message()
    setup.message(answer_type="out_of_scope")
    setup.message(answer_type=None)
    setup.message(sender="staff")
    setup.message(sender="owner", answer_type="not_found")
    setup.message(sender="system", answer_type="not_found")
    deleted = setup.new_chat(setup.store, setup.staff)
    deleted.deleted_at = START
    other = setup.new_chat(setup.other_store, setup.staff)
    for chat in [deleted, other]:
        setup.message(answer_type="not_found", chat=chat)
        setup.message(chat=chat, at=START - timedelta(days=1))
    setup.message(answer_type="out_of_scope", at=START - timedelta(days=1))
    body = setup.get().json()
    assert body["total"] == body["answered"] == 1
    assert body["lastWeekRate"] is None
    assert body["unanswered"] == []


def test_kst_week_boundaries_are_inclusive_start_exclusive_end(
    setup: StatsSetup,
) -> None:
    setup.message(at=START - timedelta(days=7, microseconds=1))
    setup.message(answer_type="not_found", at=START - timedelta(days=7))
    setup.message(at=START - timedelta(microseconds=1))
    setup.message(at=START)
    setup.message(at=START + timedelta(days=7) - timedelta(microseconds=1))
    setup.message(answer_type="not_found", at=START + timedelta(days=7))
    body = setup.get().json()
    assert body["total"] == body["answered"] == 2
    assert body["lastWeekRate"] == 50
    assert body["unanswered"] == []


@pytest.mark.parametrize("week", ["2026-11-16", "2026-11-18", "2026-11-22"])
def test_normalizes_to_monday(setup: StatsSetup, week: str) -> None:
    assert setup.get(week).json()["weekStart"] == "2026-11-16"


def test_default_week_uses_kst_date(setup: StatsSetup, monkeypatch: pytest.MonkeyPatch):
    class FrozenDatetime(datetime):
        @classmethod
        def now(cls, tz=None):
            # UTC는 일요일이지만 KST는 이미 월요일입니다.
            return START.astimezone(tz)

    monkeypatch.setattr(assistant_stats, "datetime", FrozenDatetime)
    assert setup.get(None).json()["weekStart"] == "2026-11-16"


def test_invalid_week_returns_422(setup: StatsSetup) -> None:
    assert setup.get("not-a-date").status_code == 422


def test_latest_five_questions_and_staff_name_fallback(setup: StatsSetup) -> None:
    guest = setup.user("대체 닉네임")
    chat = setup.new_chat(setup.store, guest)
    # 다른 매장의 멤버십 이름이 섞이지 않아야 합니다.
    setup.session.add(
        Membership(
            store_id=setup.other_store.id,
            user_id=guest.id,
            staff_name="다른 매장 이름",
            hourly_wage=10320,
        )
    )
    answers = []
    for i in range(7):
        at = START + timedelta(minutes=i)
        setup.message(
            sender="staff", answer_type=None, at=at, text=f"질문 {i}", chat=chat
        )
        answers.append(
            setup.message(
                answer_type="not_found", at=at + timedelta(seconds=1), chat=chat
            )
        )
    body = setup.get().json()
    assert body["total"] == 7
    assert body["answered"] == 0
    assert body["unanswered"] == [
        {
            "category": "기타",
            "questions": [
                {
                    "questionId": str(answers[i].id),
                    "question": f"질문 {i}",
                    "staffName": "대체 닉네임",
                }
                for i in range(6, 1, -1)
            ],
        }
    ]


def test_question_is_strictly_earlier_staff_message_in_same_chat(setup: StatsSetup):
    setup.message(sender="staff", at=START - timedelta(seconds=3), text="이전 질문")
    setup.message(sender="staff", at=START - timedelta(seconds=2), text="직전 질문")
    setup.message(sender="owner", at=START - timedelta(seconds=1), text="사장 답변")
    setup.message(sender="staff", at=START, text="같은 시각 질문")
    setup.message(sender="staff", at=START + timedelta(seconds=1), text="나중 질문")
    other = setup.new_chat(setup.store, setup.staff)
    setup.message(
        sender="staff", at=START - timedelta(seconds=1), text="다른 방 질문", chat=other
    )
    setup.message(answer_type="not_found")
    questions = setup.get().json()["unanswered"][0]["questions"]
    assert len(questions) == 1
    assert questions[0]["question"] == "직전 질문"


def test_missing_staff_message_preserves_unanswered_item(setup: StatsSetup) -> None:
    answer = setup.message(answer_type="not_found")
    body = setup.get().json()
    assert body["unanswered"][0]["questions"] == [
        {
            "questionId": str(answer.id),
            "question": "",
            "staffName": "지은",
        }
    ]


@pytest.mark.parametrize(("answered", "total", "rate"), [(2, 3, 67), (0, 2, 0)])
def test_previous_week_rate(setup: StatsSetup, answered: int, total: int, rate: int):
    for i in range(total):
        setup.message(
            answer_type="answered" if i < answered else "not_found",
            at=START - timedelta(days=1),
        )
    assert setup.get().json()["lastWeekRate"] == rate
