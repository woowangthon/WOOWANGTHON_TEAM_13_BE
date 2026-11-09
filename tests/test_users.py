from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.users import get_membership_service, get_user_service, router
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.user import User
from app.schemas.user import MyStoreDetail, StoreSummary


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


class StubMembershipService:
    def __init__(self) -> None:
        self.stores: list[StoreSummary] = []
        self.store_details: list[MyStoreDetail] = []

    async def list_store_summaries(self, user_id: object) -> list[StoreSummary]:
        return self.stores

    async def list_store_details(self, user_id: object) -> list[MyStoreDetail]:
        return self.store_details


def create_client() -> tuple[
    TestClient,
    StubUserService,
    StubMembershipService,
]:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    service = StubUserService()
    membership_service = StubMembershipService()

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
    test_app.dependency_overrides[get_membership_service] = (
        lambda: membership_service
    )
    return TestClient(test_app), service, membership_service


def test_get_my_profile_uses_camel_case_contract() -> None:
    client, service, _ = create_client()

    response = client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json() == {
        "userId": str(service.user.id),
        "nickname": "우왕이",
        "email": None,
        "provider": "kakao",
        "stores": [],
    }


def test_get_my_profile_embeds_actual_memberships() -> None:
    client, _, membership_service = create_client()
    store_id = uuid4()
    membership_service.stores = [
        StoreSummary(
            storeId=store_id,
            storeName="우왕 카페",
            role="owner",
            ownerName="우왕이",
            staffName=None,
            photoUrl="https://example.com/store.jpg",
        )
    ]

    response = client.get("/api/v1/users/me")

    assert response.status_code == 200
    assert response.json()["stores"] == [
        {
            "storeId": str(store_id),
            "storeName": "우왕 카페",
            "role": "owner",
            "ownerName": "우왕이",
            "staffName": None,
            "photoUrl": "https://example.com/store.jpg",
        }
    ]


def test_update_my_profile() -> None:
    client, _, _ = create_client()

    response = client.patch(
        "/api/v1/users/me",
        json={"nickname": "  새 이름  "},
    )

    assert response.status_code == 200
    assert response.json()["nickname"] == "새 이름"


def test_update_my_profile_rejects_blank_nickname() -> None:
    client, _, _ = create_client()

    response = client.patch(
        "/api/v1/users/me",
        json={"nickname": "   "},
    )

    assert response.status_code == 422


def test_withdraw_my_account() -> None:
    client, _, _ = create_client()

    response = client.delete("/api/v1/users/me")

    assert response.status_code == 204
    assert response.content == b""


def test_get_my_stores_returns_actual_memberships() -> None:
    client, _, membership_service = create_client()
    store_id = uuid4()
    member_id = uuid4()
    joined_at = datetime(2026, 11, 3, 13, 40, tzinfo=UTC)
    membership_service.store_details = [
        MyStoreDetail(
            storeId=store_id,
            name="우왕 카페",
            address="서울 마포구 와우산로 1",
            ownerName="박 사장님",
            role="staff",
            memberId=member_id,
            staffName="지은",
            photoUrl=None,
            joinedAt=joined_at,
        )
    ]

    response = client.get("/api/v1/users/me/stores")

    assert response.status_code == 200
    assert response.json() == {
        "stores": [
            {
                "storeId": str(store_id),
                "name": "우왕 카페",
                "kind": None,
                "address": "서울 마포구 와우산로 1",
                "ownerName": "박 사장님",
                "role": "staff",
                "memberId": str(member_id),
                "staffName": "지은",
                "photoUrl": None,
                "theme": None,
                "joinedAt": "2026-11-03T13:40:00Z",
            }
        ]
    }
