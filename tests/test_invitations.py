from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.invitations import get_invitation_service, router
from app.api.v1.stores import get_store_service
from app.api.v1.users import get_user_service
from app.app import app
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.invitation import Invitation
from app.models.membership import Membership
from app.models.store import Store
from app.models.user import User
from app.schemas.invitation import InvitationCreateRequest
from app.services.invitation import (
    InvitationInvalidError,
    InvitationLockedError,
    VerifiedInvitation,
)
from app.services.store import StoreNotFoundError


class StubUserService:
    def __init__(self, user: User) -> None:
        self.user = user

    async def get_or_create(self, identity: AuthenticatedUser) -> User:
        return self.user


class StubStoreService:
    def __init__(self, store: Store) -> None:
        self.store = store

    async def get_for_owner(self, store_id: UUID, owner_id: UUID) -> Store:
        if store_id != self.store.id or owner_id != self.store.owner_id:
            raise StoreNotFoundError
        return self.store


class StubInvitationService:
    def __init__(self, store: Store, owner: User) -> None:
        self.store = store
        self.owner = owner
        self.invitation = Invitation(
            id=uuid4(),
            store_id=store.id,
            created_by_user_id=owner.id,
            code="K7P2QX",
            staff_name="지은",
            hourly_wage=10_320,
            created_at=datetime.now(UTC),
        )
        self.verify_error: Exception | None = None
        self.revoked = False

    async def create(
        self,
        store: Store,
        creator_id: UUID,
        request: InvitationCreateRequest,
    ) -> Invitation:
        self.invitation.staff_name = request.staff_name
        self.invitation.hourly_wage = request.hourly_wage
        return self.invitation

    async def verify(self, code: str, user_id: UUID) -> VerifiedInvitation:
        if self.verify_error is not None:
            raise self.verify_error
        return VerifiedInvitation(self.invitation, self.store, self.owner)

    async def list_for_store(self, store_id: UUID) -> list[Invitation]:
        return [self.invitation]

    async def get_shareable(
        self,
        store_id: UUID,
        invitation_id: UUID,
    ) -> Invitation:
        return self.invitation

    async def join(self, code: str, user_id: UUID) -> tuple[Membership, Store]:
        if self.verify_error is not None:
            raise self.verify_error
        return (
            Membership(
                id=uuid4(),
                store_id=self.store.id,
                user_id=user_id,
                role="staff",
                staff_name=self.invitation.staff_name,
                hourly_wage=self.invitation.hourly_wage,
                joined_at=datetime.now(UTC),
            ),
            self.store,
        )

    async def revoke(self, store_id: UUID, invitation_id: UUID) -> None:
        self.revoked = True


def create_client() -> tuple[TestClient, StubInvitationService]:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    owner = User(
        id=uuid4(),
        auth_user_id=uuid4(),
        nickname="박 사장님",
        email=None,
        provider="kakao",
    )
    store = Store(
        id=uuid4(),
        owner_id=owner.id,
        name="달빛 카페",
        address="서울시 마포구",
        photo_url="https://example.com/store.jpg",
    )
    user_service = StubUserService(owner)
    store_service = StubStoreService(store)
    invitation_service = StubInvitationService(store, owner)

    async def authenticated_user() -> AuthenticatedUser:
        claims: Mapping[str, Any] = {}
        return AuthenticatedUser(
            id=owner.auth_user_id,
            email=None,
            role="authenticated",
            claims=claims,
        )

    test_app.dependency_overrides[get_current_user] = authenticated_user
    test_app.dependency_overrides[get_user_service] = lambda: user_service
    test_app.dependency_overrides[get_store_service] = lambda: store_service
    test_app.dependency_overrides[get_invitation_service] = (
        lambda: invitation_service
    )
    return TestClient(test_app), invitation_service


def test_invitation_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores/{store_id}/invitations" in paths
    assert "/api/v1/invitations/verify" in paths
    assert "/api/v1/memberships/join" in paths
    assert (
        "/api/v1/stores/{store_id}/invitations/{invitation_id}/share-info"
        in paths
    )


def test_owner_creates_invitation() -> None:
    client, service = create_client()

    response = client.post(
        f"/api/v1/stores/{service.store.id}/invitations",
        json={"staffName": " 지은 ", "hourlyWage": 10_320},
    )

    assert response.status_code == 201
    assert response.json() == {
        "invitationId": str(service.invitation.id),
        "storeId": str(service.store.id),
        "code": "K7P2QX",
        "staffName": "지은",
        "hourlyWage": 10_320,
        "createdAt": service.invitation.created_at.isoformat().replace(
            "+00:00",
            "Z",
        ),
    }


def test_create_rejects_wage_below_2026_minimum() -> None:
    client, service = create_client()

    response = client.post(
        f"/api/v1/stores/{service.store.id}/invitations",
        json={"staffName": "지은", "hourlyWage": 10_319},
    )

    assert response.status_code == 422


def test_owner_lists_invitations_with_status() -> None:
    client, service = create_client()

    response = client.get(
        f"/api/v1/stores/{service.store.id}/invitations"
    )

    assert response.status_code == 200
    assert response.json()["invitations"][0]["status"] == "AVAILABLE"
    assert response.json()["invitations"][0]["code"] == "K7P2QX"


def test_owner_gets_invitation_share_info() -> None:
    client, service = create_client()

    response = client.get(
        f"/api/v1/stores/{service.store.id}/invitations/"
        f"{service.invitation.id}/share-info"
    )

    assert response.status_code == 200
    assert response.json() == {
        "invitationId": str(service.invitation.id),
        "code": "K7P2QX",
        "deepLink": "/staff/join?code=K7P2QX",
    }


def test_verify_returns_frontend_contract() -> None:
    client, service = create_client()

    response = client.post(
        "/api/v1/invitations/verify",
        json={"code": "k7p2qx"},
    )

    assert response.status_code == 200
    assert response.json() == {
        "code": "K7P2QX",
        "staffName": "지은",
        "store": {
            "storeId": str(service.store.id),
            "name": "달빛 카페",
            "ownerName": "박 사장님",
            "photoUrl": "https://example.com/store.jpg",
            "theme": None,
        },
    }


def test_invalid_code_returns_frontend_error_shape() -> None:
    client, service = create_client()
    service.verify_error = InvitationInvalidError(3)

    response = client.post(
        "/api/v1/invitations/verify",
        json={"code": "ZZZZZZ"},
    )

    assert response.status_code == 404
    assert response.json() == {
        "code": "INVITE_INVALID",
        "message": "유효하지 않은 코드예요",
        "detail": {"remainingAttempts": 3},
    }


def test_locked_code_returns_unlock_time() -> None:
    client, service = create_client()
    locked_until = datetime.now(UTC) + timedelta(minutes=10)
    service.verify_error = InvitationLockedError(locked_until)

    response = client.post(
        "/api/v1/invitations/verify",
        json={"code": "ZZZZZZ"},
    )

    assert response.status_code == 429
    assert response.json()["code"] == "INVITE_LOCKED"
    assert response.json()["detail"]["lockedUntil"] == locked_until.isoformat()


def test_join_returns_membership() -> None:
    client, service = create_client()

    response = client.post(
        "/api/v1/memberships/join",
        json={"code": "K7P2QX"},
    )

    assert response.status_code == 201
    assert response.json()["storeId"] == str(service.store.id)
    assert response.json()["storeName"] == "달빛 카페"
    assert response.json()["role"] == "staff"
    assert response.json()["staffName"] == "지은"


def test_owner_revokes_invitation() -> None:
    client, service = create_client()

    response = client.delete(
        f"/api/v1/stores/{service.store.id}/invitations/"
        f"{service.invitation.id}"
    )

    assert response.status_code == 204
    assert service.revoked is True
