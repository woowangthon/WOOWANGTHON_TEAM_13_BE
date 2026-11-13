from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_active_user
from app.api.v1.push_subscriptions import get_push_service, router
from app.app import app
from app.models.push_subscription import PushSubscription
from app.models.user import User


class StubPushService:
    def __init__(self) -> None:
        self.subscribed: tuple[UUID, str, str, str] | None = None
        self.unsubscribed: tuple[UUID, str] | None = None

    async def subscribe(
        self,
        user_id: UUID,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> PushSubscription:
        self.subscribed = (user_id, endpoint, p256dh, auth)
        return PushSubscription(
            id=uuid4(),
            user_id=user_id,
            endpoint=endpoint,
            p256dh=p256dh,
            auth=auth,
        )

    async def unsubscribe(self, user_id: UUID, endpoint: str) -> None:
        self.unsubscribed = (user_id, endpoint)


def make_client() -> tuple[TestClient, StubPushService, User]:
    service = StubPushService()
    user = User(
        id=uuid4(),
        auth_user_id=uuid4(),
        nickname="지은",
        email=None,
        provider="kakao",
    )
    test_app = FastAPI()
    test_app.include_router(router)
    test_app.dependency_overrides[get_active_user] = lambda: user
    test_app.dependency_overrides[get_push_service] = lambda: service
    return TestClient(test_app), service, user


def test_push_subscription_routes_are_registered() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/users/me/push-subscriptions" in paths


def test_subscribe_to_push() -> None:
    client, service, user = make_client()
    response = client.post(
        "/users/me/push-subscriptions",
        json={
            "endpoint": "https://push.example/subscription",
            "keys": {"p256dh": "public-key", "auth": "auth-secret"},
        },
    )

    assert response.status_code == 201
    assert UUID(response.json()["subscriptionId"])
    assert service.subscribed == (
        user.id,
        "https://push.example/subscription",
        "public-key",
        "auth-secret",
    )


def test_unsubscribe_from_push() -> None:
    client, service, user = make_client()
    response = client.request(
        "DELETE",
        "/users/me/push-subscriptions",
        json={"endpoint": "https://push.example/subscription"},
    )

    assert response.status_code == 204
    assert service.unsubscribed == (user.id, "https://push.example/subscription")
