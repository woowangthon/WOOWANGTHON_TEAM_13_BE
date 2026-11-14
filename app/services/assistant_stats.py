from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from app.services.store_access import StoreAccessProtocol

SEOUL = ZoneInfo("Asia/Seoul")


@dataclass(frozen=True, slots=True)
class UnansweredQuestionView:
    question_id: UUID
    question: str
    staff_name: str


@dataclass(frozen=True, slots=True)
class AssistantStatsView:
    week_start: date
    total: int
    answered: int
    last_week_rate: int | None
    questions: list[UnansweredQuestionView]


class AssistantStatsRepositoryProtocol(Protocol):
    async def count_answers(
        self,
        store_id: UUID,
        start: datetime,
        end: datetime,
    ) -> tuple[int, int]: ...

    async def list_unanswered(
        self,
        store_id: UUID,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[UnansweredQuestionView]: ...


class AssistantStatsService:
    def __init__(
        self,
        repository: AssistantStatsRepositoryProtocol,
        store_access: StoreAccessProtocol,
    ) -> None:
        self._repository = repository
        self._store_access = store_access

    async def get_stats(
        self,
        store_id: UUID,
        user_id: UUID,
        week: date | None = None,
    ) -> AssistantStatsView:
        """사장님에게 한국 시간 기준 주간 AI 답변 통계를 반환합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        day = week if week is not None else datetime.now(SEOUL).date()
        monday = day - timedelta(days=day.weekday())
        start = datetime.combine(monday, time.min, tzinfo=SEOUL).astimezone(UTC)
        end = start + timedelta(days=7)
        total, answered = await self._repository.count_answers(store_id, start, end)
        previous_total, previous_answered = await self._repository.count_answers(
            store_id,
            start - timedelta(days=7),
            start,
        )
        questions = await self._repository.list_unanswered(store_id, start, end, 5)
        return AssistantStatsView(
            week_start=monday,
            total=total,
            answered=answered,
            last_week_rate=(
                round(previous_answered / previous_total * 100)
                if previous_total
                else None
            ),
            questions=questions,
        )
