from datetime import UTC, date, datetime, timedelta
from uuid import UUID, uuid4

from app.models.availability import Availability, AvailabilityDay
from app.models.membership import Membership
from app.models.schedule import Schedule, ScheduleRecommendation
from app.schemas.schedule import RecommendationCreateRequest
from app.services.schedule import ScheduleService

STORE_ID = uuid4()
OWNER_ID = uuid4()
NOW = datetime(2026, 11, 8, 12, tzinfo=UTC)


class FakeAccess:
    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        assert (store_id, user_id) == (STORE_ID, OWNER_ID)

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        return None


class FakeMemberships:
    def __init__(self) -> None:
        self.items = [
            Membership(
                id=uuid4(),
                store_id=STORE_ID,
                user_id=uuid4(),
                role="staff",
                staff_name=name,
                hourly_wage=10_320,
                joined_at=NOW + timedelta(minutes=index),
            )
            for index, name in enumerate(["지은", "도윤", "민수"])
        ]

    async def list_active_by_store_id(self, store_id: UUID) -> list[Membership]:
        return self.items if store_id == STORE_ID else []

    async def get_active_by_store_and_user_id(
        self, store_id: UUID, user_id: UUID
    ) -> Membership | None:
        return next((item for item in self.items if item.user_id == user_id), None)


class FakeSchedules:
    def __init__(self) -> None:
        self.availabilities: list[Availability] = []
        self.recommendations: list[ScheduleRecommendation] = []
        self.schedules: list[Schedule] = []

    async def list_availabilities(
        self, store_id: UUID, months: list[date]
    ) -> list[Availability]:
        return [
            item
            for item in self.availabilities
            if item.store_id == store_id and item.month in months
        ]

    async def create_recommendations(
        self, recommendations: list[ScheduleRecommendation]
    ) -> list[ScheduleRecommendation]:
        for recommendation in recommendations:
            recommendation.id = uuid4()
            recommendation.created_at = NOW
            for shift in recommendation.shifts:
                shift.id = uuid4()
        self.recommendations.extend(recommendations)
        return recommendations

    async def list_recommendations(
        self, store_id: UUID
    ) -> list[ScheduleRecommendation]:
        return [item for item in self.recommendations if item.store_id == store_id]

    async def get_recommendation(
        self, store_id: UUID, recommendation_id: UUID
    ) -> ScheduleRecommendation | None:
        return next(
            (
                item
                for item in self.recommendations
                if item.store_id == store_id and item.id == recommendation_id
            ),
            None,
        )

    async def get_by_recommendation(
        self, recommendation_id: UUID
    ) -> Schedule | None:
        return next(
            (
                item
                for item in self.schedules
                if item.recommendation_id == recommendation_id
            ),
            None,
        )

    async def create_schedule(self, schedule: Schedule) -> bool:
        schedule.id = uuid4()
        schedule.created_at = NOW
        schedule.updated_at = NOW
        for shift in schedule.shifts:
            shift.id = uuid4()
        self.schedules.append(schedule)
        return True

    async def get_schedule(
        self, store_id: UUID, schedule_id: UUID
    ) -> Schedule | None:
        return next(
            (
                item
                for item in self.schedules
                if item.store_id == store_id and item.id == schedule_id
            ),
            None,
        )

    async def list_schedules(
        self,
        store_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        published_only: bool = False,
    ) -> list[Schedule]:
        return [
            item
            for item in self.schedules
            if item.store_id == store_id
            and (not published_only or item.status == "published")
        ]

    async def save_schedule(self, schedule: Schedule) -> Schedule:
        return schedule


class Harness:
    def __init__(self) -> None:
        self.memberships = FakeMemberships()
        self.repository = FakeSchedules()
        self.service = ScheduleService(
            self.repository,
            self.memberships,
            FakeAccess(),
            lambda: NOW,
        )

    def submit(
        self,
        member: Membership,
        status: str | None = "available",
    ) -> None:
        availability_id = uuid4()
        self.repository.availabilities.append(
            Availability(
                id=availability_id,
                store_id=STORE_ID,
                membership_id=member.id,
                month=date(2026, 12, 1),
                memo="",
                submitted_at=NOW,
                days=(
                    [
                        AvailabilityDay(
                            availability_id=availability_id,
                            work_date=date(2026, 12, 1),
                            status=status,
                        )
                    ]
                    if status is not None
                    else []
                ),
            )
        )

    @staticmethod
    def request(required_staff: int = 1) -> RecommendationCreateRequest:
        return RecommendationCreateRequest.model_validate(
            {
                "startDate": "2026-12-01",
                "endDate": "2026-12-01",
                "recommendationCount": 3,
                "shifts": [
                    {
                        "date": "2026-12-01",
                        "start": "09:00",
                        "end": "15:00",
                        "role": "오픈",
                        "requiredStaff": required_staff,
                    }
                ],
            }
        )


async def test_overlapping_candidates_rotate_equally_available_members() -> None:
    harness = Harness()
    for member in harness.memberships.items:
        harness.submit(member)

    recommendations = await harness.service.create_recommendations(
        STORE_ID, OWNER_ID, harness.request()
    )

    assert len(recommendations) == 3
    selected = [item.shifts[0].assignments[0].membership_id for item in recommendations]
    assert selected == [member.id for member in harness.memberships.items]
    assert all(item.unfilled_slots == 0 for item in recommendations)


async def test_overlapping_shift_times_never_assign_the_same_member_twice() -> None:
    harness = Harness()
    for member in harness.memberships.items[:2]:
        harness.submit(member)
    request = RecommendationCreateRequest.model_validate(
        {
            "startDate": "2026-12-01",
            "endDate": "2026-12-01",
            "recommendationCount": 2,
            "shifts": [
                {
                    "date": "2026-12-01",
                    "start": "09:00",
                    "end": "15:00",
                    "requiredStaff": 1,
                },
                {
                    "date": "2026-12-01",
                    "start": "13:00",
                    "end": "18:00",
                    "requiredStaff": 1,
                },
            ],
        }
    )

    recommendations = await harness.service.create_recommendations(
        STORE_ID, OWNER_ID, request
    )

    assert len(recommendations) == 2
    for recommendation in recommendations:
        first_member = recommendation.shifts[0].assignments[0].membership_id
        second_member = recommendation.shifts[1].assignments[0].membership_id
        assert first_member != second_member
        assert recommendation.unfilled_slots == 0


async def test_overlapping_shift_is_left_unfilled_when_no_other_member_exists() -> None:
    harness = Harness()
    harness.submit(harness.memberships.items[0])
    request = RecommendationCreateRequest.model_validate(
        {
            "startDate": "2026-12-01",
            "endDate": "2026-12-01",
            "recommendationCount": 3,
            "shifts": [
                {
                    "date": "2026-12-01",
                    "start": "09:00",
                    "end": "15:00",
                    "requiredStaff": 1,
                },
                {
                    "date": "2026-12-01",
                    "start": "13:00",
                    "end": "18:00",
                    "requiredStaff": 1,
                },
            ],
        }
    )

    recommendations = await harness.service.create_recommendations(
        STORE_ID, OWNER_ID, request
    )

    assert len(recommendations) == 1
    assert len(recommendations[0].shifts[0].assignments) == 1
    assert recommendations[0].shifts[1].assignments == []
    assert recommendations[0].unfilled_slots == 1


async def test_unavailable_and_unmarked_members_are_not_assigned() -> None:
    harness = Harness()
    harness.submit(harness.memberships.items[0], "unavailable")
    harness.submit(harness.memberships.items[1], "available")
    harness.submit(harness.memberships.items[2], None)

    recommendations = await harness.service.create_recommendations(
        STORE_ID, OWNER_ID, harness.request(required_staff=2)
    )

    assert len(recommendations) == 1
    assignments = recommendations[0].shifts[0].assignments
    assert [item.membership_id for item in assignments] == [
        harness.memberships.items[1].id
    ]
    assert recommendations[0].unfilled_slots == 1


async def test_confirming_recommendation_copies_assignments_to_schedule() -> None:
    harness = Harness()
    harness.submit(harness.memberships.items[0])
    recommendations = await harness.service.create_recommendations(
        STORE_ID, OWNER_ID, harness.request()
    )

    schedule = await harness.service.create_schedule(
        STORE_ID,
        recommendations[0].id,
        OWNER_ID,
        "12월 첫째 주",
        publish=True,
    )

    assert schedule.status == "published"
    assert schedule.published_at == NOW
    assert schedule.recommendation_id == recommendations[0].id
    assert schedule.shifts[0].assignments[0].membership_id == (
        harness.memberships.items[0].id
    )
