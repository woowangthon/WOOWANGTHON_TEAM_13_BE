from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.invitations import get_invitation_service, router
from app.api.v1.stores import get_store_service
from app.api.v1.users import get_membership_service, get_user_service
from app.app import app
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.invitation import Invitation, InvitationScheduleAssignment
from app.models.membership import Membership
from app.models.store import Store
from app.models.user import User
from app.schemas.invitation import InvitationCreateRequest, InvitationUpdateRequest
from app.services.invitation import (
    InvitationAlreadyAvailableError,
    InvitationInvalidError,
    InvitationLockedError,
    VerifiedInvitation,
)
from app.services.membership import (
    MemberWithInvitation,
    PendingMember,
    WageBelowMinimumError,
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
        self.create_error: Exception | None = None
        self.revoked = False
        self.template_id = uuid4()

    async def create(
        self,
        store: Store,
        creator_id: UUID,
        request: InvitationCreateRequest,
    ) -> Invitation:
        if self.create_error is not None:
            raise self.create_error
        self.invitation.staff_name = request.staff_name
        self.invitation.hourly_wage = request.hourly_wage
        self.invitation.schedule = [
            InvitationScheduleAssignment(
                template_id=item.template_id,
                weekday=item.weekday,
            )
            for item in request.schedule
        ]
        return self.invitation

    async def get(self, store_id: UUID, invitation_id: UUID) -> Invitation:
        return self.invitation

    async def update(
        self,
        store_id: UUID,
        invitation_id: UUID,
        request: InvitationUpdateRequest,
    ) -> Invitation:
        if request.staff_name is not None:
            self.invitation.staff_name = request.staff_name
        if request.hourly_wage is not None:
            self.invitation.hourly_wage = request.hourly_wage
        if request.schedule is not None:
            self.invitation.schedule = [
                InvitationScheduleAssignment(
                    template_id=item.template_id,
                    weekday=item.weekday,
                )
                for item in request.schedule
            ]
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
                tax_type="none",
                joined_at=datetime.now(UTC),
            ),
            self.store,
        )

    async def revoke(self, store_id: UUID, invitation_id: UUID) -> None:
        self.revoked = True


class StubMembershipService:
    def __init__(self, store: Store, invitation_id: UUID) -> None:
        self.invitation_id = invitation_id
        self.membership = Membership(
            id=uuid4(),
            store_id=store.id,
            user_id=uuid4(),
            role="staff",
            staff_name="지은",
            hourly_wage=10_320,
            tax_type="none",
            joined_at=datetime.now(UTC),
        )
        self.pending_invitation = Invitation(
            id=uuid4(),
            store_id=store.id,
            created_by_user_id=uuid4(),
            code="M8R4TW",
            staff_name="도윤",
            hourly_wage=11_000,
            created_at=datetime.now(UTC) + timedelta(seconds=1),
        )

    async def list_members(
        self,
        store_id: UUID,
    ) -> list[MemberWithInvitation | PendingMember]:
        return [
            PendingMember(self.pending_invitation),
            MemberWithInvitation(self.membership, self.invitation_id),
        ]

    async def get_member(
        self,
        store_id: UUID,
        member_id: UUID,
    ) -> MemberWithInvitation:
        return MemberWithInvitation(self.membership, self.invitation_id)

    async def leave(self, store_id: UUID, member_id: UUID) -> Membership:
        self.membership.left_at = datetime.now(UTC)
        return self.membership

    async def update_hourly_wage(
        self,
        store_id: UUID,
        member_id: UUID,
        hourly_wage: int,
    ) -> Membership:
        if hourly_wage < 10_320:
            raise WageBelowMinimumError
        self.membership.hourly_wage = hourly_wage
        self.membership.updated_at = datetime.now(UTC)
        return self.membership


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
    membership_service = StubMembershipService(
        store,
        invitation_service.invitation.id,
    )
    invitation_service.membership_service = membership_service

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
    test_app.dependency_overrides[get_membership_service] = (
        lambda: membership_service
    )
    return TestClient(test_app), invitation_service


def test_invitation_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores/{store_id}/invitations" in paths
    assert "/api/v1/invitations/verify" in paths
    assert "/api/v1/memberships/join" in paths
    assert "/api/v1/stores/{store_id}/members" in paths
    assert "/api/v1/stores/{store_id}/members/{member_id}" in paths
    assert (
        "/api/v1/stores/{store_id}/members/{member_id}/hourly-wage" in paths
    )
    assert (
        "/api/v1/stores/{store_id}/invitations/{invitation_id}/share-info"
        in paths
    )
    assert "/api/v1/stores/{store_id}/invitations/{invitation_id}" in paths


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
        "schedule": [],
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


def test_concurrent_create_returns_existing_invitation_conflict() -> None:
    client, service = create_client()
    service.create_error = InvitationAlreadyAvailableError(service.invitation)

    response = client.post(
        f"/api/v1/stores/{service.store.id}/invitations",
        json={"staffName": "지은", "hourlyWage": 10_320},
    )

    assert response.status_code == 409
    assert response.json() == {
        "code": "INVITE_ALREADY_AVAILABLE",
        "message": "해당 직원에게 이미 사용 가능한 초대 코드가 있어요",
        "detail": {
            "invitationId": str(service.invitation.id),
            "code": "K7P2QX",
        },
    }


def test_owner_lists_invitations_with_status() -> None:
    client, service = create_client()

    response = client.get(
        f"/api/v1/stores/{service.store.id}/invitations"
    )

    assert response.status_code == 200
    assert response.json()["invitations"][0]["status"] == "AVAILABLE"
    assert response.json()["invitations"][0]["code"] == "K7P2QX"


def test_owner_creates_gets_and_updates_invitation_schedule() -> None:
    client, service = create_client()
    schedule = [{"templateId": str(service.template_id), "weekday": 2}]

    created = client.post(
        f"/api/v1/stores/{service.store.id}/invitations",
        json={
            "staffName": "지은",
            "hourlyWage": 10_320,
            "schedule": schedule,
        },
    )
    fetched = client.get(
        f"/api/v1/stores/{service.store.id}/invitations/{service.invitation.id}"
    )
    updated = client.patch(
        f"/api/v1/stores/{service.store.id}/invitations/{service.invitation.id}",
        json={"schedule": [{"templateId": str(service.template_id), "weekday": 4}]},
    )

    assert created.status_code == 201
    assert created.json()["schedule"] == schedule
    assert fetched.json()["schedule"] == schedule
    assert updated.status_code == 200
    assert updated.json()["schedule"] == [
        {"templateId": str(service.template_id), "weekday": 4}
    ]


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


def test_owner_lists_members() -> None:
    client, service = create_client()

    response = client.get(f"/api/v1/stores/{service.store.id}/members")

    assert response.status_code == 200
    members = response.json()["members"]
    assert members[0]["memberId"] is None
    assert members[0]["invitationId"] == str(
        service.membership_service.pending_invitation.id
    )
    assert members[0]["staffName"] == "도윤"
    assert members[0]["status"] == "INVITED"
    assert members[0]["joinedAt"] is None
    assert members[1]["invitationId"] == str(service.invitation.id)
    assert members[1]["status"] == "ACTIVE"
    assert members[1]["taxType"] == "none"


def test_owner_gets_member_detail() -> None:
    client, service = create_client()
    membership = service.membership_service.membership

    response = client.get(
        f"/api/v1/stores/{service.store.id}/members/{membership.id}"
    )

    assert response.status_code == 200
    assert response.json()["memberId"] == str(membership.id)
    assert response.json()["invitationId"] == str(service.invitation.id)
    assert response.json()["hourlyWage"] == 10_320


def test_owner_soft_deletes_member() -> None:
    client, service = create_client()
    membership = service.membership_service.membership

    response = client.delete(
        f"/api/v1/stores/{service.store.id}/members/{membership.id}"
    )

    assert response.status_code == 204
    assert membership.left_at is not None


def test_owner_updates_member_hourly_wage() -> None:
    client, service = create_client()
    membership = service.membership_service.membership

    response = client.put(
        f"/api/v1/stores/{service.store.id}/members/{membership.id}/hourly-wage",
        json={"hourlyWage": 12_000},
    )

    assert response.status_code == 200
    assert response.json()["memberId"] == str(membership.id)
    assert response.json()["hourlyWage"] == 12_000
    assert response.json()["updatedAt"] is not None


def test_owner_cannot_set_wage_below_2026_minimum() -> None:
    client, service = create_client()
    membership = service.membership_service.membership

    response = client.put(
        f"/api/v1/stores/{service.store.id}/members/{membership.id}/hourly-wage",
        json={"hourlyWage": 10_319},
    )

    assert response.status_code == 422
    assert response.json() == {
        "code": "WAGE_BELOW_MINIMUM",
        "message": "최저시급 10,320원보다 낮아요",
        "detail": {"minimumHourlyWage": 10_320},
    }
