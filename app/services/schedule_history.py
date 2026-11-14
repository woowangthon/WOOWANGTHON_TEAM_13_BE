"""달력·급여·대타가 공유하는 고정 근무의 날짜별 적용 규칙입니다."""

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo

from app.models.schedule import ScheduleAssignment, ShiftTemplate

SEOUL = ZoneInfo("Asia/Seoul")


def local_date(value: datetime) -> date:
    # SQLite fixtures return naive UTC timestamps; production stores UTC as well.
    return (
        (value if value.tzinfo else value.replace(tzinfo=UTC)).astimezone(SEOUL).date()
    )


def assignment_applies(assignment: ScheduleAssignment, work_date: date) -> bool:
    return (
        assignment.weekday == work_date.weekday()
        and (assignment.effective_from or date.min) <= work_date
        and (
            assignment.effective_until is None or work_date < assignment.effective_until
        )
        and (
            assignment.template.deleted_from is None
            or work_date < assignment.template.deleted_from
        )
    )


def remember_template(template: ShiftTemplate, effective_from: date) -> None:
    """같은 날 재수정해도 당일 이전 스냅샷은 한 번만 남깁니다."""
    previous_start = template.effective_from or date.min
    if previous_start < effective_from:
        template.history = [
            *(template.history or []),
            {
                "effectiveFrom": previous_start.isoformat(),
                "effectiveUntil": effective_from.isoformat(),
                "name": template.name,
                "start": template.start_time.isoformat(),
                "end": template.end_time.isoformat(),
                "role": template.role or "",
                "headcount": template.headcount or 1,
                "sortOrder": template.sort_order or 0,
            },
        ]
    template.effective_from = effective_from


def template_on(template: ShiftTemplate, work_date: date) -> ShiftTemplate:
    """ORM 원본을 수정하지 않고 해당 근무일에 유효한 시간·표시 정보를 반환합니다."""
    for item in template.history or []:
        if (
            str(item["effectiveFrom"])
            <= work_date.isoformat()
            < str(item["effectiveUntil"])
        ):
            return ShiftTemplate(
                id=template.id,
                store_id=template.store_id,
                name=str(item["name"]),
                start_time=time.fromisoformat(str(item["start"])),
                end_time=time.fromisoformat(str(item["end"])),
                role=str(item["role"]),
                headcount=int(item["headcount"]),
                sort_order=int(item["sortOrder"]),
            )
    return template
