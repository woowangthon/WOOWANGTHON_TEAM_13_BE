from datetime import UTC, date, datetime, time, timedelta
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.notifications import get_notification_service, router
from app.api.v1.users import get_user_service
from app.app import app
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.user import User
from app.services.notification import (
    SEOUL,
    SUBSTITUTE_REQUESTED,
    Notification,
    NotificationFeed,
    ShiftBanner,
    UncheckedItem,
)
from app.services.store import StoreNotFoundError

STORE_ID = uuid4()
NOW = datetime(2026, 11, 12, 8, 40, tzinfo=UTC)


class StubUserService:
    async def get_or_create(self, identity: AuthenticatedUser) -> User:
        return User(id=uuid4(), auth_user_id=uuid4(), nickname="민수", provider="kakao")


class StubNotificationService:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.read_called = False
        target = uuid4()
        self.notifications = [
            Notification(
                notification_id=f"{SUBSTITUTE_REQUESTED}:{target}",
                type=SUBSTITUTE_REQUESTED,
                title="대타 요청이 왔어요",
                body="지은님이 11/14(토) 09:00~15:00 근무 대타를 부탁했어요",
                created_at=NOW,
                target_kind="substitute_request",
                target_id=target,
            ),
            Notification(
                notification_id="old",
                type=SUBSTITUTE_REQUESTED,
                title="예전 요청",
                body="본문",
                created_at=NOW - timedelta(days=1),
                target_kind="substitute_request",
                target_id=uuid4(),
            ),
        ]
        self.banner: ShiftBanner | None = ShiftBanner(
            work_date=date(2026, 11, 12),
            start_time=time(9),
            end_time=time(15),
            starts_at=datetime(2026, 11, 12, 9, tzinfo=SEOUL),
            items=[
                UncheckedItem(
                    note_id=uuid4(),
                    item_id=uuid4(),
                    tag="재고",
                    text="우유 2팩 채우기",
                    author_name="지은",
                    work_date=date(2026, 11, 11),
                )
            ],
        )

    async def feed(self, store_id: UUID, user_id: UUID) -> NotificationFeed:
        if self.error is not None:
            raise self.error
        return NotificationFeed(
            banner=self.banner,
            notifications=self.notifications,
            unread_count=1,
            last_read_at=NOW - timedelta(hours=1),
        )

    async def mark_all_read(self, store_id: UUID, user_id: UUID) -> None:
        if self.error is not None:
            raise self.error
        self.read_called = True


def make_client() -> tuple[TestClient, StubNotificationService]:
    service = StubNotificationService()
    test_app = FastAPI()
    test_app.include_router(router)

    def authenticated_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=uuid4(), email=None, role=None, claims={})

    test_app.dependency_overrides[get_current_user] = authenticated_user
    test_app.dependency_overrides[get_user_service] = StubUserService
    test_app.dependency_overrides[get_notification_service] = lambda: service
    return TestClient(test_app), service


def url(suffix: str = "") -> str:
    return f"/stores/{STORE_ID}/notifications{suffix}"


def test_routes_are_registered_in_application() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores/{store_id}/notifications" in paths
    assert "/api/v1/stores/{store_id}/notifications/read" in paths


def test_list_notifications_shape() -> None:
    client, service = make_client()

    response = client.get(url())

    assert response.status_code == 200
    body = response.json()
    assert body["unreadCount"] == 1
    first, second = body["notifications"]
    assert set(first) == {
        "notificationId",
        "type",
        "title",
        "body",
        "createdAt",
        "isRead",
        "target",
    }
    assert first["isRead"] is False
    assert second["isRead"] is True
    assert first["target"] == {
        "kind": "substitute_request",
        "id": str(service.notifications[0].target_id),
    }
    banner = body["banner"]
    assert banner["startTime"] == "09:00"
    assert banner["endTime"] == "15:00"
    assert banner["workDate"] == "2026-11-12"
    assert banner["uncheckedCount"] == 1
    assert banner["items"][0]["text"] == "우유 2팩 채우기"
    assert banner["items"][0]["authorName"] == "지은"


def test_banner_is_null_when_not_near_shift() -> None:
    client, service = make_client()
    service.banner = None

    response = client.get(url())

    assert response.json()["banner"] is None


def test_read_notifications() -> None:
    client, service = make_client()

    response = client.post(url("/read"))

    assert response.status_code == 204
    assert service.read_called


def test_stranger_gets_404() -> None:
    client, service = make_client()
    service.error = StoreNotFoundError()

    assert client.get(url()).status_code == 404
    assert client.post(url("/read")).status_code == 404
