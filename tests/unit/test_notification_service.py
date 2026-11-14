from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

import pytest

from app.services.notification import (
    DAILY_SCHEDULE_CHANGED,
    HANDOVER_CREATED,
    MAX_NOTIFICATIONS,
    OWNER_ANSWERED,
    OWNER_QUESTION_ASKED,
    SEOUL,
    SUBSTITUTE_ACCEPTED,
    SUBSTITUTE_REJECTED,
    SUBSTITUTE_REQUESTED,
    AnswerEvent,
    HandoverEvent,
    NotificationService,
    QuestionEvent,
    ScheduleChangeEvent,
    SubstituteEvent,
    UncheckedItem,
    Viewer,
    find_banner_shift,
    is_read,
)
from app.services.store import StoreNotFoundError

STORE_ID = uuid4()
OWNER_ID = uuid4()
STAFF_ID = uuid4()
MEMBERSHIP_ID = uuid4()
# 2026-11-12(목) 08:40 KST
NOW = datetime(2026, 11, 12, 8, 40, tzinfo=SEOUL).astimezone(UTC)
TODAY = date(2026, 11, 12)


def at(minutes_ago: int) -> datetime:
    return NOW - timedelta(minutes=minutes_ago)


class FakeRepository:
    def __init__(self) -> None:
        self.received: list[SubstituteEvent] = []
        self.accepted: list[SubstituteEvent] = []
        self.rejected: list[SubstituteEvent] = []
        self.changes: list[ScheduleChangeEvent] = []
        self.answers: list[AnswerEvent] = []
        self.handovers: list[HandoverEvent] = []
        self.questions: list[QuestionEvent] = []
        self.unchecked: list[UncheckedItem] = []
        self.unchecked_range: tuple[date, date] | None = None
        self.last_read: datetime | None = None
        self.since_seen: list[datetime] = []
        self.handover_excluded: UUID | None = None

    async def get_viewer(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> tuple[Viewer, UUID | None] | None:
        if store_id != STORE_ID:
            return None
        if user_id == OWNER_ID:
            return "owner", None
        if user_id == STAFF_ID:
            return "staff", MEMBERSHIP_ID
        return None

    async def list_received_substitutes(
        self, store_id: UUID, user_id: UUID, since: datetime
    ) -> list[SubstituteEvent]:
        self.since_seen.append(since)
        return self.received

    async def list_accepted_substitutes(
        self, store_id: UUID, user_id: UUID, since: datetime
    ) -> list[SubstituteEvent]:
        return self.accepted

    async def list_rejected_substitutes(
        self, store_id: UUID, user_id: UUID, since: datetime
    ) -> list[SubstituteEvent]:
        return self.rejected

    async def list_schedule_changes(
        self, store_id: UUID, user_id: UUID, since: datetime
    ) -> list[ScheduleChangeEvent]:
        return self.changes

    async def list_answered_questions(
        self, store_id: UUID, user_id: UUID, since: datetime
    ) -> list[AnswerEvent]:
        return self.answers

    async def list_handovers(
        self, store_id: UUID, exclude_user_id: UUID, since: datetime
    ) -> list[HandoverEvent]:
        self.handover_excluded = exclude_user_id
        return self.handovers

    async def list_owner_questions(
        self, store_id: UUID, since: datetime
    ) -> list[QuestionEvent]:
        return self.questions

    async def list_unchecked_items(
        self, store_id: UUID, start_date: date, end_date: date
    ) -> list[UncheckedItem]:
        self.unchecked_range = (start_date, end_date)
        return self.unchecked

    async def get_last_read_at(self, store_id: UUID, user_id: UUID) -> datetime | None:
        return self.last_read

    async def mark_read(self, store_id: UUID, user_id: UUID, read_at: datetime) -> None:
        self.last_read = read_at


class FakeShifts:
    def __init__(self) -> None:
        self.shifts: list[tuple[date, time, time]] = []
        self.asked: tuple[UUID, date, date] | None = None

    async def list_user_shift_times(
        self,
        store_id: UUID,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[tuple[date, time, time]]:
        self.asked = (user_id, start_date, end_date)
        return self.shifts


class Harness:
    def __init__(self, now: datetime = NOW) -> None:
        self.repository = FakeRepository()
        self.shifts = FakeShifts()
        self.service = NotificationService(
            self.repository,
            self.shifts,
            clock=lambda: now,
        )


def substitute(name: str, minutes_ago: int) -> SubstituteEvent:
    return SubstituteEvent(
        request_id=uuid4(),
        work_date=date(2026, 11, 14),
        start_time=time(9),
        end_time=time(15),
        other_name=name,
        at=at(minutes_ago),
    )


def unchecked_item(text: str) -> UncheckedItem:
    return UncheckedItem(
        note_id=uuid4(),
        item_id=uuid4(),
        tag="재고",
        text=text,
        author_name="민지",
        work_date=TODAY - timedelta(days=1),
    )


@pytest.fixture
def harness() -> Harness:
    return Harness()


async def test_staff_feed_has_substitutes_and_answers_newest_first(
    harness: Harness,
) -> None:
    received = substitute("민수", 30)
    accepted = substitute("지은", 10)
    answer = AnswerEvent(uuid4(), uuid4(), "우산 빌려줘도 돼요?", at(20))
    harness.repository.received = [received]
    harness.repository.accepted = [accepted]
    harness.repository.answers = [answer]

    feed = await harness.service.feed(STORE_ID, STAFF_ID)

    assert [item.type for item in feed.notifications] == [
        SUBSTITUTE_ACCEPTED,
        OWNER_ANSWERED,
        SUBSTITUTE_REQUESTED,
    ]
    accepted_item, answer_item, received_item = feed.notifications
    assert received_item.body == "민수님이 11/14(토) 09:00~15:00 근무 대타를 부탁했어요"
    assert received_item.target_kind == "substitute_request"
    assert received_item.target_id == received.request_id
    assert accepted_item.body == "지은님이 11/14(토) 09:00~15:00 근무를 대신해요"
    assert answer_item.title == "사장님이 답했어요"
    assert answer_item.body == "우산 빌려줘도 돼요?"
    assert answer_item.target_kind == "assistant_chat"
    assert answer_item.target_id == answer.chat_id
    assert harness.repository.since_seen == [NOW - timedelta(days=14)]


async def test_owner_feed_has_handovers_and_questions(harness: Harness) -> None:
    harness.repository.handovers = [
        HandoverEvent(
            uuid4(), "민지", "우유 2팩 남음 " * 10, at(5), TODAY - timedelta(days=3)
        )
    ]
    harness.repository.questions = [
        QuestionEvent(uuid4(), "민수", "쓰레받기 어딨어?", at(1))
    ]
    harness.shifts.shifts = [(TODAY, time(9), time(15))]

    feed = await harness.service.feed(STORE_ID, OWNER_ID)

    question_item, handover_item = feed.notifications
    assert question_item.type == OWNER_QUESTION_ASKED
    assert question_item.title == "민수님의 질문"
    assert question_item.target_kind == "owner_question"
    assert handover_item.work_date == TODAY - timedelta(days=3)
    assert handover_item.type == HANDOVER_CREATED
    assert handover_item.title == "민지님이 인수인계를 남겼어요"
    assert handover_item.body.endswith("…")
    assert len(handover_item.body) <= 61
    assert harness.repository.handover_excluded == OWNER_ID


async def test_owner_gets_banner_before_own_shift(harness: Harness) -> None:
    harness.shifts.shifts = [(TODAY, time(9), time(15))]
    harness.repository.unchecked = [unchecked_item("우유 2팩 채우기")]

    feed = await harness.service.feed(STORE_ID, OWNER_ID)

    assert feed.banner is not None
    assert (feed.banner.start_time, feed.banner.end_time) == (time(9), time(15))
    assert [item.text for item in feed.banner.items] == ["우유 2팩 채우기"]
    assert harness.shifts.asked == (OWNER_ID, TODAY, TODAY)


async def test_owner_without_shift_has_no_banner(harness: Harness) -> None:
    feed = await harness.service.feed(STORE_ID, OWNER_ID)

    assert feed.banner is None
    assert harness.repository.unchecked_range is None


async def test_staff_feed_has_rejected_substitute(harness: Harness) -> None:
    rejected = substitute("지은", 3)
    harness.repository.rejected = [rejected]

    feed = await harness.service.feed(STORE_ID, STAFF_ID)

    (item,) = feed.notifications
    assert item.type == SUBSTITUTE_REJECTED
    assert item.notification_id == f"SUBSTITUTE_REJECTED:{rejected.request_id}"
    assert item.title == "대타 요청이 거절됐어요"
    assert item.body == "지은님이 11/14(토) 09:00~15:00 근무 대타를 거절했어요"
    assert item.target_kind == "substitute_request"
    assert item.target_id == rejected.request_id


async def test_staff_feed_has_daily_schedule_changes(harness: Harness) -> None:
    work_date = date(2026, 11, 18)
    added = ScheduleChangeEvent(uuid4(), work_date, "ADDED", "오픈 10:00~13:00", at(3))
    removed = ScheduleChangeEvent(
        uuid4(), work_date, "REMOVED", "마감 18:00~22:00", at(2)
    )
    changed = ScheduleChangeEvent(
        uuid4(), work_date, "CHANGED", "오픈 10:00~13:00", at(1)
    )
    harness.repository.changes = [added, removed, changed]

    feed = await harness.service.feed(STORE_ID, STAFF_ID)

    assert [item.type for item in feed.notifications] == [DAILY_SCHEDULE_CHANGED] * 3
    assert [item.body for item in feed.notifications] == [
        "11/18(수) 근무가 바뀌었어요 · 오픈 10:00~13:00",
        "11/18(수) 근무가 빠졌어요 · 마감 18:00~22:00",
        "11/18(수) 근무가 생겼어요 · 오픈 10:00~13:00",
    ]
    assert feed.notifications[0].title == "근무가 바뀌었어요"
    assert feed.notifications[0].target_kind == "daily_schedule"
    assert feed.notifications[0].target_id == changed.notice_id


async def test_stranger_gets_not_found(harness: Harness) -> None:
    with pytest.raises(StoreNotFoundError):
        await harness.service.feed(STORE_ID, uuid4())
    with pytest.raises(StoreNotFoundError):
        await harness.service.mark_all_read(STORE_ID, uuid4())


async def test_unread_count_uses_last_read_time(harness: Harness) -> None:
    harness.repository.received = [substitute("민수", 30), substitute("지은", 5)]
    harness.repository.last_read = at(10)

    feed = await harness.service.feed(STORE_ID, STAFF_ID)

    assert feed.unread_count == 1
    assert [is_read(item, feed.last_read_at) for item in feed.notifications] == [
        False,
        True,
    ]


async def test_everything_is_unread_before_first_read(harness: Harness) -> None:
    harness.repository.received = [substitute("민수", 30)]

    feed = await harness.service.feed(STORE_ID, STAFF_ID)

    assert feed.unread_count == 1


async def test_mark_all_read_saves_current_time(harness: Harness) -> None:
    harness.repository.received = [substitute("민수", 1)]

    await harness.service.mark_all_read(STORE_ID, STAFF_ID)
    feed = await harness.service.feed(STORE_ID, STAFF_ID)

    assert harness.repository.last_read == NOW
    assert feed.unread_count == 0


async def test_feed_is_capped(harness: Harness) -> None:
    harness.repository.received = [
        substitute("민수", minutes) for minutes in range(MAX_NOTIFICATIONS + 5)
    ]

    feed = await harness.service.feed(STORE_ID, STAFF_ID)

    assert len(feed.notifications) == MAX_NOTIFICATIONS
    assert feed.notifications[0].created_at == at(0)


async def test_banner_shows_unchecked_items_30_minutes_before_shift() -> None:
    harness = Harness(datetime(2026, 11, 12, 8, 30, tzinfo=SEOUL))
    harness.shifts.shifts = [(TODAY, time(9), time(15))]
    harness.repository.unchecked = [unchecked_item("우유 2팩 채우기")]

    feed = await harness.service.feed(STORE_ID, STAFF_ID)

    assert feed.banner is not None
    assert (feed.banner.start_time, feed.banner.end_time) == (time(9), time(15))
    assert feed.banner.starts_at == datetime(2026, 11, 12, 9, tzinfo=SEOUL)
    assert [item.text for item in feed.banner.items] == ["우유 2팩 채우기"]
    assert harness.shifts.asked == (STAFF_ID, TODAY, TODAY)
    assert harness.repository.unchecked_range == (TODAY - timedelta(days=7), TODAY)


async def test_banner_is_hidden_outside_shift_window() -> None:
    too_early = Harness(datetime(2026, 11, 12, 8, 29, tzinfo=SEOUL))
    after_end = Harness(datetime(2026, 11, 12, 15, 0, tzinfo=SEOUL))
    for harness in (too_early, after_end):
        harness.shifts.shifts = [(TODAY, time(9), time(15))]

        feed = await harness.service.feed(STORE_ID, STAFF_ID)

        assert feed.banner is None
        assert harness.repository.unchecked_range is None


async def test_banner_uses_korean_date_near_midnight_utc() -> None:
    # 2026-11-12 08:45 KST는 UTC로 11/11 23:45다
    harness = Harness(datetime(2026, 11, 11, 23, 45, tzinfo=UTC))
    harness.shifts.shifts = [(TODAY, time(9), time(15))]

    feed = await harness.service.feed(STORE_ID, STAFF_ID)

    assert feed.banner is not None
    assert harness.shifts.asked == (STAFF_ID, TODAY, TODAY)


def test_find_banner_shift_picks_current_or_next_shift() -> None:
    morning = (TODAY, time(9), time(12))
    evening = (TODAY, time(18), time(22))
    shifts = [evening, morning]

    def local(hour: int, minute: int = 0) -> datetime:
        return datetime(2026, 11, 12, hour, minute, tzinfo=SEOUL)

    assert find_banner_shift(shifts, local(8, 30)) == morning
    assert find_banner_shift(shifts, local(11, 59)) == morning
    assert find_banner_shift(shifts, local(12)) is None
    assert find_banner_shift(shifts, local(17, 30)) == evening
    assert find_banner_shift([], local(9)) is None
