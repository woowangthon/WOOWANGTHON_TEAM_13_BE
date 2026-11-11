from collections.abc import Callable, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Literal, Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from app.services.owner_question import question_title
from app.services.store import StoreNotFoundError

SEOUL = ZoneInfo("Asia/Seoul")
LOOKBACK = timedelta(days=14)
MAX_NOTIFICATIONS = 50
BANNER_LEAD = timedelta(minutes=30)
HANDOVER_LOOKBACK_DAYS = 7
SUMMARY_MAX_LENGTH = 60
WEEKDAYS = "월화수목금토일"

Viewer = Literal["owner", "staff"]

SUBSTITUTE_REQUESTED = "SUBSTITUTE_REQUESTED"
SUBSTITUTE_ACCEPTED = "SUBSTITUTE_ACCEPTED"
SUBSTITUTE_REJECTED = "SUBSTITUTE_REJECTED"
DAILY_SCHEDULE_CHANGED = "DAILY_SCHEDULE_CHANGED"
OWNER_ANSWERED = "OWNER_ANSWERED"
HANDOVER_CREATED = "HANDOVER_CREATED"
OWNER_QUESTION_ASKED = "OWNER_QUESTION_ASKED"


@dataclass(frozen=True, slots=True)
class SubstituteEvent:
    """대타 요청과 상대방 이름, 알림 시각입니다."""

    request_id: UUID
    work_date: date
    start_time: time
    end_time: time
    other_name: str
    at: datetime


@dataclass(frozen=True, slots=True)
class ScheduleChangeEvent:
    """사장님이 바꾼 내 하루 근무입니다."""

    notice_id: UUID
    work_date: date
    change: str
    shifts_text: str
    at: datetime


@dataclass(frozen=True, slots=True)
class AnswerEvent:
    """사장님이 답한 내 질문입니다."""

    question_id: UUID
    chat_id: UUID
    question: str
    at: datetime


@dataclass(frozen=True, slots=True)
class HandoverEvent:
    """알바생이 남긴 인수인계입니다."""

    note_id: UUID
    author_name: str
    summary: str
    at: datetime


@dataclass(frozen=True, slots=True)
class QuestionEvent:
    """알바생이 사장님께 넘긴 질문입니다."""

    question_id: UUID
    staff_name: str
    question: str
    at: datetime


@dataclass(frozen=True, slots=True)
class UncheckedItem:
    """아직 아무도 체크하지 않은 인수인계 항목입니다."""

    note_id: UUID
    item_id: UUID
    tag: str
    text: str
    author_name: str
    work_date: date


@dataclass(frozen=True, slots=True)
class Notification:
    """알림 목록의 항목 하나입니다."""

    notification_id: str
    type: str
    title: str
    body: str
    created_at: datetime
    target_kind: str
    target_id: UUID


@dataclass(frozen=True, slots=True)
class ShiftBanner:
    """출근 30분 전부터 퇴근까지 보여 줄 인수인계 요약입니다."""

    work_date: date
    start_time: time
    end_time: time
    starts_at: datetime
    items: list[UncheckedItem]


@dataclass(frozen=True, slots=True)
class NotificationFeed:
    """알림 화면에 필요한 배너, 목록, 안 읽은 개수입니다."""

    banner: ShiftBanner | None
    notifications: list[Notification]
    unread_count: int
    last_read_at: datetime | None


class NotificationRepositoryProtocol(Protocol):
    async def get_viewer(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> tuple[Viewer, UUID | None] | None: ...

    async def list_received_substitutes(
        self,
        store_id: UUID,
        user_id: UUID,
        since: datetime,
    ) -> list[SubstituteEvent]: ...

    async def list_accepted_substitutes(
        self,
        store_id: UUID,
        user_id: UUID,
        since: datetime,
    ) -> list[SubstituteEvent]: ...

    async def list_rejected_substitutes(
        self,
        store_id: UUID,
        user_id: UUID,
        since: datetime,
    ) -> list[SubstituteEvent]: ...

    async def list_schedule_changes(
        self,
        store_id: UUID,
        user_id: UUID,
        since: datetime,
    ) -> list[ScheduleChangeEvent]: ...

    async def list_answered_questions(
        self,
        store_id: UUID,
        user_id: UUID,
        since: datetime,
    ) -> list[AnswerEvent]: ...

    async def list_handovers(
        self,
        store_id: UUID,
        exclude_user_id: UUID,
        since: datetime,
    ) -> list[HandoverEvent]: ...

    async def list_owner_questions(
        self,
        store_id: UUID,
        since: datetime,
    ) -> list[QuestionEvent]: ...

    async def list_unchecked_items(
        self,
        store_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[UncheckedItem]: ...

    async def get_last_read_at(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> datetime | None: ...

    async def mark_read(
        self,
        store_id: UUID,
        user_id: UUID,
        read_at: datetime,
    ) -> None: ...


class ShiftLookupProtocol(Protocol):
    async def list_user_shift_times(
        self,
        store_id: UUID,
        user_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[tuple[date, time, time]]: ...


def _day(value: date) -> str:
    """날짜를 11/12(목) 형식으로 씁니다."""
    return f"{value.month}/{value.day}({WEEKDAYS[value.weekday()]})"


def _shift(event: SubstituteEvent) -> str:
    """대타 근무 날짜와 시간을 한 줄로 씁니다."""
    start = event.start_time.strftime("%H:%M")
    end = event.end_time.strftime("%H:%M")
    return f"{_day(event.work_date)} {start}~{end}"


SCHEDULE_CHANGE_VERBS = {
    "ADDED": "생겼어요",
    "REMOVED": "빠졌어요",
    "CHANGED": "바뀌었어요",
}


def _schedule_change_body(event: ScheduleChangeEvent) -> str:
    """'11/18(수) 근무가 바뀌었어요 · 오픈 10:00~13:00' 형식으로 씁니다."""
    verb = SCHEDULE_CHANGE_VERBS.get(event.change, "바뀌었어요")
    return f"{_day(event.work_date)} 근무가 {verb} · {event.shifts_text}"


def _shorten(text: str) -> str:
    """긴 요약을 알림 본문 길이로 줄입니다."""
    flat = " ".join(text.split())
    if len(flat) <= SUMMARY_MAX_LENGTH:
        return flat
    return flat[:SUMMARY_MAX_LENGTH].rstrip() + "…"


def is_read(notification: Notification, last_read_at: datetime | None) -> bool:
    """알림이 마지막으로 알림 화면을 연 시각 이전에 생겼는지 확인합니다."""
    return last_read_at is not None and notification.created_at <= last_read_at


def find_banner_shift(
    shifts: Sequence[tuple[date, time, time]],
    now: datetime,
) -> tuple[date, time, time] | None:
    """출근 30분 전부터 퇴근 전까지에 해당하는 가장 이른 근무를 찾습니다."""
    for work_date, start, end in sorted(shifts):
        starts_at = datetime.combine(work_date, start, SEOUL)
        ends_at = datetime.combine(work_date, end, SEOUL)
        if starts_at - BANNER_LEAD <= now < ends_at:
            return work_date, start, end
    return None


class NotificationService:
    def __init__(
        self,
        repository: NotificationRepositoryProtocol,
        shifts: ShiftLookupProtocol,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """알림을 모으는 데 필요한 저장소와 현재 시각 함수를 받습니다."""
        self._repository = repository
        self._shifts = shifts
        self._clock = clock or (lambda: datetime.now(UTC))

    async def _viewer(
        self, store_id: UUID, user_id: UUID
    ) -> tuple[Viewer, UUID | None]:
        """사장님인지 재직 중인 알바생인지 확인하고 아니면 404로 처리합니다."""
        viewer = await self._repository.get_viewer(store_id, user_id)
        if viewer is None:
            raise StoreNotFoundError
        return viewer

    async def feed(self, store_id: UUID, user_id: UUID) -> NotificationFeed:
        """내 역할에 맞는 알림 목록과 출근 전 배너를 만듭니다."""
        role, _ = await self._viewer(store_id, user_id)
        now = self._clock()
        since = now - LOOKBACK
        if role == "owner":
            items = await self._owner_items(store_id, user_id, since)
        else:
            items = await self._staff_items(store_id, user_id, since)
        banner = await self._banner(store_id, user_id, now)
        items.sort(
            key=lambda item: (item.created_at, item.notification_id), reverse=True
        )
        items = items[:MAX_NOTIFICATIONS]
        last_read = await self._repository.get_last_read_at(store_id, user_id)
        unread = sum(1 for item in items if not is_read(item, last_read))
        return NotificationFeed(banner, items, unread, last_read)

    async def mark_all_read(self, store_id: UUID, user_id: UUID) -> None:
        """지금까지의 알림을 모두 읽음으로 표시합니다."""
        await self._viewer(store_id, user_id)
        await self._repository.mark_read(store_id, user_id, self._clock())

    async def _staff_items(
        self,
        store_id: UUID,
        user_id: UUID,
        since: datetime,
    ) -> list[Notification]:
        """알바생이 받을 대타, 대타 결과, 근무 변경, 사장님 답변 알림을 모읍니다."""
        received = await self._repository.list_received_substitutes(
            store_id, user_id, since
        )
        accepted = await self._repository.list_accepted_substitutes(
            store_id, user_id, since
        )
        rejected = await self._repository.list_rejected_substitutes(
            store_id, user_id, since
        )
        changes = await self._repository.list_schedule_changes(store_id, user_id, since)
        answers = await self._repository.list_answered_questions(
            store_id, user_id, since
        )
        items = [
            Notification(
                notification_id=f"{SUBSTITUTE_REQUESTED}:{event.request_id}",
                type=SUBSTITUTE_REQUESTED,
                title="대타 요청이 왔어요",
                body=f"{event.other_name}님이 {_shift(event)} 근무 대타를 부탁했어요",
                created_at=event.at,
                target_kind="substitute_request",
                target_id=event.request_id,
            )
            for event in received
        ]
        items += [
            Notification(
                notification_id=f"{SUBSTITUTE_ACCEPTED}:{event.request_id}",
                type=SUBSTITUTE_ACCEPTED,
                title="대타가 구해졌어요",
                body=f"{event.other_name}님이 {_shift(event)} 근무를 대신해요",
                created_at=event.at,
                target_kind="substitute_request",
                target_id=event.request_id,
            )
            for event in accepted
        ]
        items += [
            Notification(
                notification_id=f"{SUBSTITUTE_REJECTED}:{event.request_id}",
                type=SUBSTITUTE_REJECTED,
                title="대타 요청이 거절됐어요",
                body=f"{event.other_name}님이 {_shift(event)} 근무 대타를 거절했어요",
                created_at=event.at,
                target_kind="substitute_request",
                target_id=event.request_id,
            )
            for event in rejected
        ]
        items += [
            Notification(
                notification_id=f"{DAILY_SCHEDULE_CHANGED}:{event.notice_id}",
                type=DAILY_SCHEDULE_CHANGED,
                title="근무가 바뀌었어요",
                body=_schedule_change_body(event),
                created_at=event.at,
                target_kind="daily_schedule",
                target_id=event.notice_id,
            )
            for event in changes
        ]
        items += [
            Notification(
                notification_id=f"{OWNER_ANSWERED}:{event.question_id}",
                type=OWNER_ANSWERED,
                title="사장님이 답했어요",
                body=question_title(event.question),
                created_at=event.at,
                target_kind="assistant_chat",
                target_id=event.chat_id,
            )
            for event in answers
        ]
        return items

    async def _owner_items(
        self,
        store_id: UUID,
        user_id: UUID,
        since: datetime,
    ) -> list[Notification]:
        """사장님이 받을 새 인수인계와 새 질문 알림을 모읍니다."""
        handovers = await self._repository.list_handovers(store_id, user_id, since)
        questions = await self._repository.list_owner_questions(store_id, since)
        items = [
            Notification(
                notification_id=f"{HANDOVER_CREATED}:{event.note_id}",
                type=HANDOVER_CREATED,
                title=f"{event.author_name}님이 인수인계를 남겼어요",
                body=_shorten(event.summary),
                created_at=event.at,
                target_kind="handover",
                target_id=event.note_id,
            )
            for event in handovers
        ]
        items += [
            Notification(
                notification_id=f"{OWNER_QUESTION_ASKED}:{event.question_id}",
                type=OWNER_QUESTION_ASKED,
                title=f"{event.staff_name}님의 질문",
                body=question_title(event.question),
                created_at=event.at,
                target_kind="owner_question",
                target_id=event.question_id,
            )
            for event in questions
        ]
        return items

    async def _banner(
        self,
        store_id: UUID,
        user_id: UUID,
        now: datetime,
    ) -> ShiftBanner | None:
        """사장님 포함 내 근무 30분 전부터 퇴근 전까지 체크 안 된 항목을 모읍니다."""
        local_now = now.astimezone(SEOUL)
        today = local_now.date()
        shifts = await self._shifts.list_user_shift_times(
            store_id, user_id, today, today
        )
        shift = find_banner_shift(shifts, local_now)
        if shift is None:
            return None
        work_date, start, end = shift
        items = await self._repository.list_unchecked_items(
            store_id,
            today - timedelta(days=HANDOVER_LOOKBACK_DAYS),
            today,
        )
        return ShiftBanner(
            work_date=work_date,
            start_time=start,
            end_time=end,
            starts_at=datetime.combine(work_date, start, SEOUL),
            items=items,
        )
