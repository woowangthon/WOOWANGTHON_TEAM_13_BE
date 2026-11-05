from collections.abc import Mapping
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.users import get_user_service, router
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.user import User


class StubUserService:
    def __init__(self) -> None:
        self.user = User(
            id=uuid4(),
            auth_user_id=uuid4(),
            nickname="우왕이",
            email=None,
            provider="kakao",
        )

    async def get_or_create(self, identity: AuthenticatedUser) -> User:
        return self.user

    async def update_nickname(
        self,
        identity: AuthenticatedUser,
        nickname: str,
    ) -> User:
        self.user.nickname = nickname
        return self.user

    async def withdraw(self, identity: AuthenticatedUser) -> None:
        return None


def create_client() -> tuple[TestClient, StubUserService]:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    service = StubUserService()

    async def authenticated_user() -> AuthenticatedUser:
        claims: Mapping[str, Any] = {}
        return AuthenticatedUser(
            id=service.user.auth_user_id,
            email=None,
            role="authenticated",
            claims=claims,
        )

    test_app.dependency_overrides[get_current_user] = authenticated_user
    test_app.dependency_overrides[get_user_service] = lambda: service
    return TestClient(test_app), service


def test_get_my_profile_uses_camel_case_contract() -> None:
    client, service = create_client()

    response = client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json() == {
        "userId": str(service.user.id),
        "nickname": "우왕이",
        "email": None,
        "provider": "kakao",
        "stores": [],
    }


def test_update_my_profile() -> None:
    client, _ = create_client()

    response = client.patch(
        "/api/v1/users/me",
        json={"nickname": "  새 이름  "},
    )

    assert response.status_code == 200
    assert response.json()["nickname"] == "새 이름"


def test_update_my_profile_rejects_blank_nickname() -> None:
    client, _ = create_client()

    response = client.patch(
        "/api/v1/users/me",
        json={"nickname": "   "},
    )

    assert response.status_code == 422


def test_withdraw_my_account() -> None:
    client, _ = create_client()

    response = client.delete("/api/v1/users/me")

    assert response.status_code == 204
    assert response.content == b""


def test_get_my_stores_returns_empty_list_until_memberships_exist() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/users/me/stores")

    assert response.status_code == 200
    assert response.json() == []
