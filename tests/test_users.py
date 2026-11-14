from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.users import get_membership_service, get_user_service, router
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.user import User
from app.schemas.user import MyStoreDetail, StoreSummary
from app.services.user import UserService


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


class InMemoryUserRepository:
    def __init__(self, users: list[User]) -> None:
        self.users = users

    async def get_by_auth_user_id(
        self,
        auth_user_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        for user in self.users:
            if user.auth_user_id != auth_user_id:
                continue
            if not include_deleted and user.deleted_at is not None:
                return None
            return user
        return None

    async def create(self, user: User) -> User:
        user.id = uuid4()
        self.users.append(user)
        return user

    async def save(self, user: User) -> User:
        return user


class UserBoundMembershipService(StubMembershipService):
    def __init__(self, stores_by_user: dict[UUID, list[StoreSummary]]) -> None:
        super().__init__()
        self.stores_by_user = stores_by_user

    async def list_store_summaries(self, user_id: UUID) -> list[StoreSummary]:
        return self.stores_by_user.get(user_id, [])


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


def test_withdraw_then_relogin_creates_fresh_user_without_old_stores() -> None:
    auth_user_id = uuid4()
    old_user = User(
        id=uuid4(),
        auth_user_id=auth_user_id,
        nickname="기존 사용자",
        email="old@example.com",
        provider="kakao",
    )
    old_user_id = old_user.id
    old_store_id = uuid4()
    repository = InMemoryUserRepository([old_user])
    service = UserService(repository)
    membership_service = UserBoundMembershipService(
        {
            old_user_id: [
                StoreSummary(
                    storeId=old_store_id,
                    storeName="옛 매장",
                    role="owner",
                    ownerName="기존 사용자",
                    staffName=None,
                    photoUrl=None,
                )
            ]
        }
    )
    identity = AuthenticatedUser(
        id=auth_user_id,
        email="new@example.com",
        role="authenticated",
        claims={
            "app_metadata": {"provider": "kakao"},
            "user_metadata": {"nickname": "새 사용자"},
        },
    )
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    test_app.dependency_overrides[get_current_user] = lambda: identity
    test_app.dependency_overrides[get_user_service] = lambda: service
    test_app.dependency_overrides[get_membership_service] = (
        lambda: membership_service
    )
    client = TestClient(test_app)

    before = client.get("/api/v1/users/me")
    assert before.status_code == 200
    assert before.json()["stores"][0]["storeId"] == str(old_store_id)

    withdrawn = client.delete("/api/v1/users/me")
    relogged_in = client.get("/api/v1/users/me")

    assert withdrawn.status_code == 204
    assert relogged_in.status_code == 200
    assert relogged_in.json()["stores"] == []
    assert relogged_in.json()["userId"] != str(old_user_id)
    assert old_user.id == old_user_id
    assert old_user.auth_user_id != auth_user_id
    assert old_user.nickname == "탈퇴한 사용자"
    assert old_user.email is None
    assert old_user.deleted_at is not None
    assert membership_service.stores_by_user[old_user_id][0].store_id == (
        old_store_id
    )
    assert len(repository.users) == 2
    assert repository.users[0] is old_user
    assert repository.users[1].auth_user_id == auth_user_id
    assert repository.users[1].deleted_at is None


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
