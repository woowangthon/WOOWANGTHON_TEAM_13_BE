from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_active_user
from app.api.v1.business_verifications import (
    get_business_verification_service,
    router,
)
from app.models.business_verification import BusinessVerification
from app.models.user import User
from app.schemas.business_verification import BusinessVerificationCreateRequest
from app.services.business_verification import BusinessVerificationNotFoundError


class StubBusinessVerificationService:
    def __init__(self, user_id: UUID) -> None:
        self.user_id = user_id
        self.verification = BusinessVerification(
            id=101,
            requester_id=user_id,
            business_registration_number="1234567890",
            owner_name=None,
            business_start_date=None,
            status="VERIFIED",
            provider_message="확인되었습니다.",
            created_at=datetime(2026, 11, 10, tzinfo=UTC),
        )

    async def create(
        self,
        requester_id: UUID,
        request: BusinessVerificationCreateRequest,
    ) -> BusinessVerification:
        self.verification.requester_id = requester_id
        self.verification.business_registration_number = (
            request.business_registration_number
        )
        return self.verification

    async def get_for_requester(
        self,
        verification_id: int,
        requester_id: UUID,
    ) -> BusinessVerification:
        if verification_id != self.verification.id or requester_id != self.user_id:
            raise BusinessVerificationNotFoundError
        return self.verification


def create_client() -> tuple[TestClient, StubBusinessVerificationService]:
    test_app = FastAPI()
    test_app.include_router(router, prefix="/api/v1")
    user = User(
        id=uuid4(),
        auth_user_id=uuid4(),
        nickname="홍길동",
        email=None,
        provider="kakao",
    )
    service = StubBusinessVerificationService(user.id)
    test_app.dependency_overrides[get_active_user] = lambda: user
    test_app.dependency_overrides[get_business_verification_service] = lambda: service
    return TestClient(test_app), service


def test_create_business_verification() -> None:
    client, _ = create_client()

    response = client.post(
        "/api/v1/stores/business-verifications",
        json={
            "businessRegistrationNumber": "123-45-67890",
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "verificationId": 101,
        "businessRegistrationNumber": "1234567890",
        "ownerName": None,
        "businessStartDate": None,
        "status": "VERIFIED",
        "message": "확인되었습니다.",
        "createdAt": "2026-11-10T00:00:00Z",
    }


def test_get_business_verification() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/stores/business-verifications/101")

    assert response.status_code == 200
    assert response.json()["status"] == "VERIFIED"


def test_get_unknown_business_verification_returns_404() -> None:
    client, _ = create_client()

    response = client.get("/api/v1/stores/business-verifications/999")

    assert response.status_code == 404


def test_rejects_invalid_business_registration_number() -> None:
    client, _ = create_client()

    response = client.post(
        "/api/v1/stores/business-verifications",
        json={
            "businessRegistrationNumber": "1234",
        },
    )

    assert response.status_code == 422
