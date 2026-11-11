from datetime import date, time
from uuid import UUID, uuid4

from app.schemas.schedule import DailyScheduleShiftInput
from app.services.schedule import ScheduleService
from app.services.schedule_change import (
    DayShift,
    ScheduleChange,
    diff_day_shifts,
    shifts_text,
)
from tests.unit.test_schedule_service import (
    NOW,
    OWNER_ID,
    STAFF_ID,
    STORE_ID,
    WORK_DATE,
    StubAccess,
    StubRepository,
)

OTHER_ID = uuid4()


def shift(user_id: UUID, start: int, end: int, name: str = "오픈") -> DayShift:
    return DayShift(time(start), time(end), name, user_id)


class FakeRecorder:
    def __init__(self, fail: bool = False) -> None:
        self.records: list[tuple[UUID, date, list[ScheduleChange]]] = []
        self.fail = fail

    async def record(
        self, store_id: UUID, work_date: date, changes: list[ScheduleChange]
    ) -> None:
        if self.fail:
            raise RuntimeError("db down")
        self.records.append((store_id, work_date, changes))


def test_shifts_text_lists_shifts_in_time_order() -> None:
    text = shifts_text([shift(STAFF_ID, 18, 22, "마감"), shift(STAFF_ID, 10, 13)])

    assert text == "오픈 10:00~13:00, 마감 18:00~22:00"


def test_diff_finds_added_removed_and_changed_workers() -> None:
    before = [shift(STAFF_ID, 10, 14), shift(OTHER_ID, 18, 22, "마감")]
    after = [shift(STAFF_ID, 11, 14), shift(OWNER_ID, 18, 22, "마감")]
    newcomer = uuid4()
    after.append(shift(newcomer, 14, 18, "미들"))

    changes = diff_day_shifts(before, after, OWNER_ID)

    found = {change.user_id: (change.change, change.shifts_text) for change in changes}
    assert found == {
        STAFF_ID: ("CHANGED", "오픈 11:00~14:00"),
        OTHER_ID: ("REMOVED", "마감 18:00~22:00"),
        newcomer: ("ADDED", "미들 14:00~18:00"),
    }


def test_diff_skips_unchanged_workers_and_the_owner_who_changed_it() -> None:
    same = [shift(STAFF_ID, 10, 14), shift(OWNER_ID, 14, 18)]

    assert diff_day_shifts(same, [shift(STAFF_ID, 10, 14)], OWNER_ID) == []


async def test_replacing_daily_schedule_records_changes() -> None:
    repository = StubRepository()
    recorder = FakeRecorder()
    service = ScheduleService(
        repository, StubAccess(), clock=lambda: NOW, change_recorder=recorder
    )

    await service.replace_daily_schedule(
        STORE_ID,
        OWNER_ID,
        WORK_DATE,
        [
            DailyScheduleShiftInput(
                template_id=repository.template.id,
                assignee_user_id=STAFF_ID,
                start="11:30",
                end="16:30",
            )
        ],
    )

    [(store_id, work_date, changes)] = recorder.records
    assert (store_id, work_date) == (STORE_ID, WORK_DATE)
    assert changes == [ScheduleChange(STAFF_ID, "CHANGED", "오픈 11:30~16:30")]


async def test_resetting_daily_schedule_records_return_to_fixed_shift() -> None:
    repository = StubRepository()
    recorder = FakeRecorder()
    service = ScheduleService(
        repository, StubAccess(), clock=lambda: NOW, change_recorder=recorder
    )
    await service.replace_daily_schedule(STORE_ID, OWNER_ID, WORK_DATE, [])
    recorder.records.clear()

    await service.reset_daily_schedule(STORE_ID, OWNER_ID, WORK_DATE)

    [(_, _, changes)] = recorder.records
    assert changes == [ScheduleChange(STAFF_ID, "ADDED", "오픈 10:00~14:00")]


async def test_recording_failure_keeps_schedule_change() -> None:
    repository = StubRepository()
    service = ScheduleService(
        repository,
        StubAccess(),
        clock=lambda: NOW,
        change_recorder=FakeRecorder(fail=True),
    )

    await service.replace_daily_schedule(STORE_ID, OWNER_ID, WORK_DATE, [])

    assert WORK_DATE in repository.day_overrides
