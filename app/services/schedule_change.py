from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass
from datetime import date, time
from typing import Literal, Protocol
from uuid import UUID

ChangeKind = Literal["ADDED", "REMOVED", "CHANGED"]
SHIFTS_TEXT_MAX_LENGTH = 300


@dataclass(frozen=True, slots=True, order=True)
class DayShift:
    """하루 근무표의 근무 한 칸입니다."""

    start_time: time
    end_time: time
    name: str
    assignee_user_id: UUID


@dataclass(frozen=True, slots=True)
class ScheduleChange:
    """하루 근무 변경으로 근무가 달라진 직원 한 명의 변경 내용입니다."""

    user_id: UUID
    change: ChangeKind
    shifts_text: str


class ScheduleChangeRecorderProtocol(Protocol):
    async def record(
        self,
        store_id: UUID,
        work_date: date,
        changes: list[ScheduleChange],
    ) -> None: ...


def shifts_text(shifts: Iterable[DayShift]) -> str:
    """근무 칸을 '오픈 10:00~13:00, 마감 18:00~22:00' 형식으로 씁니다."""
    text = ", ".join(
        f"{shift.name} {shift.start_time:%H:%M}~{shift.end_time:%H:%M}"
        for shift in sorted(shifts)
    )
    return text[:SHIFTS_TEXT_MAX_LENGTH]


def diff_day_shifts(
    before: Iterable[DayShift],
    after: Iterable[DayShift],
    actor_user_id: UUID,
) -> list[ScheduleChange]:
    """바뀌기 전후 근무를 비교해 근무가 생기거나 빠지거나 바뀐 직원을 찾습니다."""
    before_by_user: dict[UUID, list[DayShift]] = defaultdict(list)
    after_by_user: dict[UUID, list[DayShift]] = defaultdict(list)
    for shift in before:
        before_by_user[shift.assignee_user_id].append(shift)
    for shift in after:
        after_by_user[shift.assignee_user_id].append(shift)

    changes: list[ScheduleChange] = []
    for user_id in sorted(set(before_by_user) | set(after_by_user)):
        if user_id == actor_user_id:
            continue
        old = sorted(before_by_user.get(user_id, []))
        new = sorted(after_by_user.get(user_id, []))
        if old == new:
            continue
        if not old:
            changes.append(ScheduleChange(user_id, "ADDED", shifts_text(new)))
        elif not new:
            changes.append(ScheduleChange(user_id, "REMOVED", shifts_text(old)))
        else:
            changes.append(ScheduleChange(user_id, "CHANGED", shifts_text(new)))
    return changes
