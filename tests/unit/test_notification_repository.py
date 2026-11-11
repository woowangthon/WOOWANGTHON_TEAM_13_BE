from collections.abc import Iterator
from datetime import UTC, date, datetime, time, timedelta
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
from app.models.handover import HandoverItem, HandoverNote
from app.models.membership import Membership
from app.models.notification import NotificationRead, ScheduleChangeNotice
from app.models.owner_question import OwnerQuestion
from app.models.schedule import (
    ScheduleAssignment,
    ScheduleAssignmentOverride,
    ShiftTemplate,
    SubstituteRequest,
)
from app.models.store import Store
from app.models.user import User
from app.repositories.notification import NotificationRepository
from app.repositories.schedule_change import ScheduleChangeRepository
from app.services.schedule_change import ScheduleChange

NOW = datetime(2026, 11, 12, 0, tzinfo=UTC)
SINCE = NOW - timedelta(days=14)
WORK_DATE = date(2026, 11, 14)


@compiles(JSONB, "sqlite")
def _jsonb_as_json(_type: Any, _compiler: Any, **_kw: Any) -> str:
    return "JSON"


class SyncSessionAdapter:
    """실제 쿼리를 SQLite에서 실행하도록 동기 세션을 감쌉니다."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, query: Any) -> Any:
        return self._session.execute(query)

    def add(self, item: Any) -> None:
        self._session.add(item)

    def add_all(self, items: Any) -> None:
        self._session.add_all(items)

    async def commit(self) -> None:
        self._session.commit()

    async def rollback(self) -> None:
        self._session.rollback()


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
        HandoverNote.__table__,
        HandoverItem.__table__,
        ShiftTemplate.__table__,
        ScheduleAssignment.__table__,
        SubstituteRequest.__table__,
        ScheduleAssignmentOverride.__table__,
        NotificationRead.__table__,
        ScheduleChangeNotice.__table__,
    ]
    User.metadata.create_all(engine, tables=tables)
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session
    engine.dispose()


def repo(session: Session) -> NotificationRepository:
    return NotificationRepository(cast(AsyncSession, SyncSessionAdapter(session)))


class World:
    """매장 하나와 사장님, 알바생 두 명을 만듭니다."""

    def __init__(self, session: Session) -> None:
        self.session = session
        self.owner_id = self.user("사장님닉네임")
        self.store = Store(
            id=uuid4(), owner_id=self.owner_id, name="매장", address="주소"
        )
        session.add(self.store)
        self.minsu = self.user("카카오민수")
        self.jieun = self.user("카카오지은")
        self.minsu_member = self.member(self.minsu, "민수")
        self.jieun_member = self.member(self.jieun, "지은")
        self.template = ShiftTemplate(
            id=uuid4(),
            store_id=self.store.id,
            name="오픈",
            start_time=time(9),
            end_time=time(15),
        )
        self.assignment = ScheduleAssignment(
            id=uuid4(),
            store_id=self.store.id,
            template_id=self.template.id,
            weekday=WORK_DATE.weekday(),
            assignee_user_id=self.minsu,
        )
        session.add_all([self.template, self.assignment])
        session.commit()

    def user(self, nickname: str) -> UUID:
        user = User(
            id=uuid4(), auth_user_id=uuid4(), nickname=nickname, provider="kakao"
        )
        self.session.add(user)
        return user.id

    def member(self, user_id: UUID, name: str, left: bool = False) -> Membership:
        membership = Membership(
            id=uuid4(),
            store_id=self.store.id,
            user_id=user_id,
            role="staff",
            staff_name=name,
            hourly_wage=10320,
            joined_at=NOW,
            left_at=NOW if left else None,
        )
        self.session.add(membership)
        return membership

    def substitute(
        self,
        requester: UUID,
        target: UUID,
        status: str = "PENDING",
        created_at: datetime = NOW,
        responded_at: datetime | None = None,
        week: int = 0,
    ) -> SubstituteRequest:
        request = SubstituteRequest(
            id=uuid4(),
            store_id=self.store.id,
            schedule_assignment_id=self.assignment.id,
            work_date=WORK_DATE + timedelta(weeks=week),
            requester_user_id=requester,
            target_user_id=target,
            status=status,
            created_at=created_at,
            responded_at=responded_at,
        )
        self.session.add(request)
        self.session.commit()
        return request

    def handover(
        self,
        author: UUID,
        items: list[tuple[str, bool]],
        work_date: date = date(2026, 11, 11),
        deleted: bool = False,
        created_at: datetime = NOW,
    ) -> HandoverNote:
        note = HandoverNote(
            id=uuid4(),
            store_id=self.store.id,
            author_id=author,
            work_date=work_date,
            raw_text="원문",
            no_issue=False,
            summary="우유 부족",
            created_at=created_at,
            deleted_at=NOW if deleted else None,
            items=[
                HandoverItem(
                    id=uuid4(), position=index, tag="재고", text=text, checked=checked
                )
                for index, (text, checked) in enumerate(items)
            ],
        )
        self.session.add(note)
        self.session.commit()
        return note

    def question(
        self,
        asked_by: UUID,
        status: str = "asked",
        answered_at: datetime | None = None,
    ) -> OwnerQuestion:
        chat = AssistantChat(
            id=uuid4(), store_id=self.store.id, user_id=asked_by, last_message_at=NOW
        )
        message = AssistantMessage(
            id=uuid4(),
            chat_id=chat.id,
            sender="ai",
            text="못 찾음",
            answer_type="not_found",
            sources=[],
            created_at=NOW,
        )
        question = OwnerQuestion(
            id=uuid4(),
            store_id=self.store.id,
            chat_id=chat.id,
            message_id=message.id,
            asked_by=asked_by,
            question="쓰레받기 어딨어?",
            status=status,
            answer="창고" if answered_at else None,
            answered_at=answered_at,
            created_at=NOW,
        )
        self.session.add_all([chat, message, question])
        self.session.commit()
        return question


@pytest.fixture
def world(session: Session) -> World:
    return World(session)


async def test_viewer_role(session: Session, world: World) -> None:
    left = world.user("퇴사자")
    world.member(left, "퇴사", left=True)
    session.commit()
    repository = repo(session)

    assert await repository.get_viewer(world.store.id, world.owner_id) == (
        "owner",
        None,
    )
    assert await repository.get_viewer(world.store.id, world.minsu) == (
        "staff",
        world.minsu_member.id,
    )
    assert await repository.get_viewer(world.store.id, left) is None
    assert await repository.get_viewer(world.store.id, uuid4()) is None
    assert await repository.get_viewer(uuid4(), world.owner_id) is None


async def test_received_substitutes_use_requester_name_and_skip_cancelled(
    session: Session,
    world: World,
) -> None:
    pending = world.substitute(world.minsu, world.jieun)
    world.substitute(world.minsu, world.jieun, status="CANCELLED")
    world.substitute(
        world.minsu, world.jieun, created_at=SINCE - timedelta(days=1), week=1
    )
    world.substitute(world.jieun, world.minsu, week=2)

    events = await repo(session).list_received_substitutes(
        world.store.id, world.jieun, SINCE
    )

    [event] = events
    assert event.request_id == pending.id
    assert event.other_name == "민수"
    assert (event.work_date, event.start_time, event.end_time) == (
        WORK_DATE,
        time(9),
        time(15),
    )


async def test_accepted_substitutes_go_to_requester(
    session: Session,
    world: World,
) -> None:
    responded = NOW + timedelta(minutes=5)
    accepted = world.substitute(
        world.minsu, world.jieun, status="ACCEPTED", responded_at=responded
    )
    world.substitute(world.minsu, world.jieun, status="REJECTED", responded_at=NOW)

    events = await repo(session).list_accepted_substitutes(
        world.store.id, world.minsu, SINCE
    )

    [event] = events
    assert event.request_id == accepted.id
    assert event.other_name == "지은"
    assert event.at.replace(tzinfo=UTC) == responded


async def test_answered_questions_only_mine(session: Session, world: World) -> None:
    mine = world.question(world.minsu, status="answered", answered_at=NOW)
    world.question(world.minsu)
    world.question(world.jieun, status="answered", answered_at=NOW)

    events = await repo(session).list_answered_questions(
        world.store.id, world.minsu, SINCE
    )

    assert [event.question_id for event in events] == [mine.id]
    assert events[0].chat_id == mine.chat_id


async def test_owner_sees_staff_handovers_and_questions(
    session: Session,
    world: World,
) -> None:
    note = world.handover(world.minsu, [("우유", False)])
    world.handover(world.owner_id, [("사장님 메모", False)])
    world.handover(world.jieun, [("삭제됨", False)], deleted=True)
    question = world.question(world.jieun)
    repository = repo(session)

    handovers = await repository.list_handovers(world.store.id, world.owner_id, SINCE)
    questions = await repository.list_owner_questions(world.store.id, SINCE)

    assert [(event.note_id, event.author_name) for event in handovers] == [
        (note.id, "민수")
    ]
    assert [(event.question_id, event.staff_name) for event in questions] == [
        (question.id, "지은")
    ]


async def test_unchecked_items_in_date_range(session: Session, world: World) -> None:
    recent = world.handover(
        world.minsu,
        [("우유 채우기", False), ("완료됨", True), ("컵 채우기", False)],
        work_date=date(2026, 11, 11),
    )
    older = world.handover(world.jieun, [("시럽", False)], work_date=date(2026, 11, 6))
    world.handover(world.jieun, [("너무 옛날", False)], work_date=date(2026, 11, 1))
    world.handover(world.jieun, [("삭제", False)], deleted=True)

    items = await repo(session).list_unchecked_items(
        world.store.id, date(2026, 11, 5), date(2026, 11, 12)
    )

    assert [(item.note_id, item.text, item.author_name) for item in items] == [
        (recent.id, "우유 채우기", "민수"),
        (recent.id, "컵 채우기", "민수"),
        (older.id, "시럽", "지은"),
    ]


async def test_mark_read_creates_then_moves_forward(
    session: Session,
    world: World,
) -> None:
    repository = repo(session)
    later = NOW + timedelta(hours=1)

    assert await repository.get_last_read_at(world.store.id, world.minsu) is None
    await repository.mark_read(world.store.id, world.minsu, later)
    await repository.mark_read(world.store.id, world.minsu, NOW)

    saved = await repository.get_last_read_at(world.store.id, world.minsu)
    assert saved is not None
    assert saved.replace(tzinfo=UTC) == later
    assert await repository.get_last_read_at(world.store.id, world.jieun) is None


async def test_rejected_substitutes_go_to_requester(
    session: Session,
    world: World,
) -> None:
    responded = NOW + timedelta(minutes=5)
    rejected = world.substitute(
        world.minsu, world.jieun, status="REJECTED", responded_at=responded
    )
    world.substitute(
        world.minsu, world.jieun, status="ACCEPTED", responded_at=NOW, week=1
    )
    world.substitute(
        world.jieun, world.minsu, status="REJECTED", responded_at=NOW, week=2
    )

    events = await repo(session).list_rejected_substitutes(
        world.store.id, world.minsu, SINCE
    )

    [event] = events
    assert event.request_id == rejected.id
    assert event.other_name == "지은"
    assert event.at.replace(tzinfo=UTC) == responded


async def test_schedule_change_notices_are_recorded_and_listed_per_user(
    session: Session,
    world: World,
) -> None:
    recorder = ScheduleChangeRepository(cast(AsyncSession, SyncSessionAdapter(session)))
    await recorder.record(
        world.store.id,
        date(2026, 11, 18),
        [
            ScheduleChange(world.minsu, "CHANGED", "오픈 10:00~13:00"),
            ScheduleChange(world.jieun, "REMOVED", "마감 18:00~22:00"),
        ],
    )
    await recorder.record(world.store.id, date(2026, 11, 19), [])

    events = await repo(session).list_schedule_changes(
        world.store.id, world.minsu, NOW - timedelta(days=365 * 10)
    )

    [event] = events
    assert event.work_date == date(2026, 11, 18)
    assert (event.change, event.shifts_text) == ("CHANGED", "오픈 10:00~13:00")
    assert session.query(ScheduleChangeNotice).count() == 2
    assert (
        await repo(session).list_schedule_changes(
            uuid4(), world.minsu, NOW - timedelta(days=365 * 10)
        )
        == []
    )
