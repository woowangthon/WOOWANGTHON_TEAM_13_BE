from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_active_user
from app.api.v1.availabilities import get_availability_service, router
from app.app import app
from app.models.availability import Availability, AvailabilityDay
from app.models.membership import Membership
from app.models.user import User
from app.services.availability import (
    AvailabilityClosedError,
    AvailabilityExistsError,
    AvailabilityNotFoundError,
    AvailabilityPeriod,
    AvailabilityStaffOnlyError,
    AvailabilitySubmissionView,
    AvailabilityView,
    StoreAvailabilityView,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError

STORE_ID = uuid4()
USER_ID = uuid4()
MEMBER_ID = uuid4()
AVAILABILITY_ID = uuid4()
NOW = datetime(2026, 11, 20, 12, tzinfo=UTC)
PERIOD = AvailabilityPeriod(date(2026, 12, 1), date(2026, 11, 25))


def make_membership() -> Membership:
    return Membership(
        id=MEMBER_ID,
        store_id=STORE_ID,
        user_id=USER_ID,
        role="staff",
        staff_name="지은",
        hourly_wage=10_320,
        joined_at=NOW,
    )


def make_availability() -> Availability:
    return Availability(
        id=AVAILABILITY_ID,
        store_id=STORE_ID,
        membership_id=MEMBER_ID,
        month=PERIOD.month,
        memo="기말고사",
        submitted_at=NOW,
        days=[
            AvailabilityDay(
                availability_id=AVAILABILITY_ID,
                work_date=date(2026, 12, 15),
                status="unavailable",
            )
        ],
    )


class StubAvailabilityService:
    def __init__(self) -> None:
        self.availability: Availability | None = None
        self.error: Exception | None = None
        self.seen_create: tuple[str, int, str] | None = None
        self.seen_update: tuple[UUID, int, str] | None = None

    def _raise(self) -> None:
        if self.error is not None:
            raise self.error

    async def get_mine(self, store_id: UUID, user_id: UUID) -> AvailabilityView:
        self._raise()
        return AvailabilityView(PERIOD, self.availability)

    async def create(
        self,
        store_id: UUID,
        user_id: UUID,
        month_key: str,
        days: list[object],
        memo: str,
    ) -> AvailabilityView:
        self._raise()
        self.seen_create = (month_key, len(days), memo)
        self.availability = make_availability()
        return AvailabilityView(PERIOD, self.availability)

    async def update(
        self,
        store_id: UUID,
        availability_id: UUID,
        user_id: UUID,
        days: list[object],
        memo: str,
    ) -> AvailabilityView:
        self._raise()
        self.seen_update = (availability_id, len(days), memo)
        self.availability = make_availability()
        return AvailabilityView(PERIOD, self.availability)

    async def delete(
        self,
        store_id: UUID,
        availability_id: UUID,
        user_id: UUID,
    ) -> None:
        self._raise()

    async def list_store_availabilities(
        self,
        store_id: UUID,
        owner_id: UUID,
        month_key: str | None,
    ) -> tuple[AvailabilityPeriod, list[StoreAvailabilityView]]:
        self._raise()
        availability = make_availability()
        return PERIOD, [
            StoreAvailabilityView(make_membership(), availability, PERIOD)
        ]

    async def list_submissions(
        self,
        store_id: UUID,
        owner_id: UUID,
        month_key: str | None,
    ) -> tuple[AvailabilityPeriod, list[AvailabilitySubmissionView]]:
        self._raise()
        return PERIOD, [
            AvailabilitySubmissionView(make_membership(), self.availability)
        ]


def make_client() -> tuple[TestClient, StubAvailabilityService]:
    service = StubAvailabilityService()
    test_app = FastAPI()
    test_app.include_router(router)
    test_app.dependency_overrides[get_active_user] = lambda: User(
        id=USER_ID,
        auth_user_id=uuid4(),
        nickname="지은",
        provider="kakao",
    )
    test_app.dependency_overrides[get_availability_service] = lambda: service
    return TestClient(test_app), service


def url(suffix: str) -> str:
    return f"/stores/{STORE_ID}{suffix}"


def test_availability_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores/{store_id}/availabilities/me" in paths
    assert "/api/v1/stores/{store_id}/availabilities" in paths
    assert "/api/v1/stores/{store_id}/availabilities/{availability_id}" in paths
    assert "/api/v1/stores/{store_id}/availability-submissions" in paths


def test_get_my_availability_before_submission() -> None:
    client, _ = make_client()

    response = client.get(url("/availabilities/me"))

    assert response.status_code == 200
    assert response.json() == {
        "availabilityId": None,
        "month": "2026-12",
        "deadline": "2026-11-25",
        "days": [],
        "memo": "",
        "submittedAt": None,
    }


def test_create_availability_uses_fe_contract() -> None:
    client, service = make_client()

    response = client.post(
        url("/availabilities"),
        json={
            "month": "2026-12",
            "days": [{"date": "2026-12-15", "status": "unavailable"}],
            "memo": " 기말고사 ",
        },
    )

    assert response.status_code == 201
    assert response.json()["availabilityId"] == str(AVAILABILITY_ID)
    assert response.json()["days"] == [
        {"date": "2026-12-15", "status": "unavailable"}
    ]
    assert service.seen_create == ("2026-12", 1, "기말고사")


def test_create_rejects_day_outside_month_and_duplicates() -> None:
    client, _ = make_client()
    base = {"month": "2026-12", "memo": ""}

    outside = client.post(
        url("/availabilities"),
        json={
            **base,
            "days": [{"date": "2027-01-01", "status": "available"}],
        },
    )
    duplicate = client.post(
        url("/availabilities"),
        json={
            **base,
            "days": [
                {"date": "2026-12-01", "status": "available"},
                {"date": "2026-12-01", "status": "unavailable"},
            ],
        },
    )

    assert outside.status_code == 422
    assert duplicate.status_code == 422


def test_update_and_delete() -> None:
    client, service = make_client()

    updated = client.patch(
        url(f"/availabilities/{AVAILABILITY_ID}"),
        json={
            "days": [{"date": "2026-12-20", "status": "available"}],
            "memo": "수정",
        },
    )
    deleted = client.delete(url(f"/availabilities/{AVAILABILITY_ID}"))

    assert updated.status_code == 200
    assert deleted.status_code == 204
    assert service.seen_update == (AVAILABILITY_ID, 1, "수정")


def test_domain_error_codes() -> None:
    client, service = make_client()

    service.error = AvailabilityExistsError()
    exists = client.post(
        url("/availabilities"),
        json={"month": "2026-12", "days": [], "memo": ""},
    )
    service.error = AvailabilityClosedError()
    closed = client.post(
        url("/availabilities"),
        json={"month": "2026-12", "days": [], "memo": ""},
    )
    service.error = AvailabilityNotFoundError()
    missing = client.patch(
        url(f"/availabilities/{AVAILABILITY_ID}"),
        json={"days": [], "memo": ""},
    )
    service.error = AvailabilityStaffOnlyError()
    forbidden = client.get(url("/availabilities/me"))

    assert (exists.status_code, exists.json()["code"]) == (
        409,
        "AVAILABILITY_EXISTS",
    )
    assert (closed.status_code, closed.json()["code"]) == (
        409,
        "AVAILABILITY_CLOSED",
    )
    assert (missing.status_code, missing.json()["code"]) == (404, "NOT_FOUND")
    assert (forbidden.status_code, forbidden.json()["code"]) == (403, "FORBIDDEN")


def test_access_errors() -> None:
    client, service = make_client()

    service.error = StoreAccessForbiddenError()
    forbidden = client.get(url("/availabilities"))
    service.error = StoreNotFoundError()
    missing = client.get(url("/availabilities"))

    assert forbidden.status_code == 403
    assert missing.status_code == 404


def test_owner_lists_availabilities_and_submission_status() -> None:
    client, service = make_client()
    service.availability = make_availability()

    submitted = client.get(url("/availabilities"), params={"month": "2026-12"})
    status_response = client.get(
        url("/availability-submissions"),
        params={"month": "2026-12"},
    )

    assert submitted.status_code == 200
    assert submitted.json()["availabilities"][0]["staffName"] == "지은"
    assert status_response.status_code == 200
    assert status_response.json()["totalMembers"] == 1
    assert status_response.json()["submittedCount"] == 1
    assert status_response.json()["members"][0]["submitted"] is True


def test_owner_month_query_format_is_validated() -> None:
    client, _ = make_client()

    response = client.get(url("/availabilities"), params={"month": "2026-1"})

    assert response.status_code == 422
