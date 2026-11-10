from collections.abc import Mapping
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.stores import get_store_service, router
from app.api.v1.users import get_user_service
from app.app import app
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.store import Store
from app.models.user import User
from app.schemas.store import StoreCreateRequest, StoreUpdateRequest
from app.services.store import (
    BusinessVerificationRequiredError,
    StoreNotFoundError,
)


class StubUserService:
    def __init__(self) -> None:
        self.user = User(
            id=uuid4(),
            auth_user_id=uuid4(),
            nickname="홍길동",
            email="owner@example.com",
            provider="kakao",
        )

    async def get_or_create(self, identity: AuthenticatedUser) -> User:
        return self.user


class StubStoreService:
    def __init__(self, owner_id: UUID) -> None:
        self.owner_id = owner_id
        self.store = Store(
            id=uuid4(),
            owner_id=owner_id,
            name="우왕 카페 강남점",
            address="서울특별시 강남구 테헤란로 123",
            business_verification_id=101,
            photo_url="https://example.com/store.jpg",
            payday=10,
            business_size="UNDER_FIVE",
        )
        self.deleted = False
        self.reject_verification = False

    async def create(
        self,
        owner_id: UUID,
        request: StoreCreateRequest,
    ) -> Store:
        if self.reject_verification:
            raise BusinessVerificationRequiredError
        self.store = Store(
            id=uuid4(),
            owner_id=owner_id,
            name=request.name,
            address=request.address,
            business_verification_id=request.business_verification_id,
            photo_url=request.photo_url,
            payday=request.payday,
            business_size=request.business_size,
        )
        return self.store

    async def list_for_owner(self, owner_id: UUID) -> list[Store]:
        if owner_id != self.owner_id or self.deleted:
            return []
        return [self.store]

    async def get_for_owner(self, store_id: UUID, owner_id: UUID) -> Store:
        if store_id != self.store.id or owner_id != self.owner_id or self.deleted:
            raise StoreNotFoundError
        return self.store

    async def update(
        self,
        store_id: UUID,
        owner_id: UUID,
        request: StoreUpdateRequest,
    ) -> Store:
        store = await self.get_for_owner(store_id, owner_id)
        for field, value in request.model_dump(exclude_unset=True).items():
            setattr(store, field, value)
        return store

    async def delete(self, store_id: UUID, owner_id: UUID) -> None:
        await self.get_for_owner(store_id, owner_id)
        self.deleted = True


def create_client() -> tuple[TestClient, StubUserService, StubStoreService]:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    user_service = StubUserService()
    store_service = StubStoreService(user_service.user.id)

    async def authenticated_user() -> AuthenticatedUser:
        claims: Mapping[str, Any] = {}
        return AuthenticatedUser(
            id=user_service.user.auth_user_id,
            email=user_service.user.email,
            role="authenticated",
            claims=claims,
        )

    test_app.dependency_overrides[get_current_user] = authenticated_user
    test_app.dependency_overrides[get_user_service] = lambda: user_service
    test_app.dependency_overrides[get_store_service] = lambda: store_service
    return TestClient(test_app), user_service, store_service


def test_store_routes_are_registered_in_application() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores" in paths
    assert "/api/v1/stores/{store_id}" in paths


def test_create_store_uses_camel_case_contract() -> None:
    client, _, store_service = create_client()

    response = client.post(
        "/api/v1/stores",
        json={
            "name": "  새 매장  ",
            "address": "  서울특별시 마포구 1  ",
            "businessVerificationId": 202,
            "photoUrl": "https://example.com/new-store.jpg",
            "payday": 25,
            "businessSize": "FIVE_OR_MORE",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "storeId": str(store_service.store.id),
        "name": "새 매장",
        "address": "서울특별시 마포구 1",
        "ownerName": "홍길동",
        "businessVerificationId": 202,
        "photoUrl": "https://example.com/new-store.jpg",
        "payday": 25,
        "businessSize": "FIVE_OR_MORE",
    }


def test_create_store_requires_business_verification_id() -> None:
    client, _, _ = create_client()

    response = client.post(
        "/api/v1/stores",
        json={
            "name": "새 매장",
            "address": "서울특별시 마포구 1",
        },
    )

    assert response.status_code == 422


def test_create_store_rejects_unverified_business() -> None:
    client, _, store_service = create_client()
    store_service.reject_verification = True

    response = client.post(
        "/api/v1/stores",
        json={
            "name": "새 매장",
            "address": "서울특별시 마포구 1",
            "businessVerificationId": 202,
        },
    )

    assert response.status_code == 400
    assert response.json() == {"detail": "A verified business registration is required"}


def test_list_stores_returns_wrapper() -> None:
    client, _, store_service = create_client()

    response = client.get("/api/v1/stores")

    assert response.status_code == 200
    assert response.json()["stores"][0]["storeId"] == str(store_service.store.id)


def test_get_store_detail() -> None:
    client, _, store_service = create_client()

    response = client.get(f"/api/v1/stores/{store_service.store.id}")

    assert response.status_code == 200
    assert response.json()["name"] == "우왕 카페 강남점"
    assert response.json()["ownerName"] == "홍길동"


def test_get_unknown_store_returns_404() -> None:
    client, _, _ = create_client()

    response = client.get(f"/api/v1/stores/{uuid4()}")

    assert response.status_code == 404
    assert response.json() == {"detail": "Store not found"}


def test_update_store() -> None:
    client, _, store_service = create_client()

    response = client.patch(
        f"/api/v1/stores/{store_service.store.id}",
        json={
            "name": "  수정한 매장  ",
            "photoUrl": None,
            "payday": 31,
            "businessSize": "UNDER_FIVE",
        },
    )

    assert response.status_code == 200
    assert response.json()["name"] == "수정한 매장"
    assert response.json()["photoUrl"] is None
    assert response.json()["address"] == "서울특별시 강남구 테헤란로 123"
    assert response.json()["payday"] == 31
    assert response.json()["businessSize"] == "UNDER_FIVE"


def test_store_rejects_invalid_payday() -> None:
    client, _, store_service = create_client()

    response = client.patch(
        f"/api/v1/stores/{store_service.store.id}",
        json={"payday": 30},
    )

    assert response.status_code == 422


def test_store_rejects_invalid_business_size() -> None:
    client, _, store_service = create_client()

    response = client.patch(
        f"/api/v1/stores/{store_service.store.id}",
        json={"businessSize": "TEN_OR_MORE"},
    )

    assert response.status_code == 422


def test_update_store_rejects_empty_body() -> None:
    client, _, store_service = create_client()

    response = client.patch(
        f"/api/v1/stores/{store_service.store.id}",
        json={},
    )

    assert response.status_code == 422


def test_delete_store() -> None:
    client, _, store_service = create_client()

    response = client.delete(f"/api/v1/stores/{store_service.store.id}")

    assert response.status_code == 204
    assert response.content == b""
    assert store_service.deleted is True
