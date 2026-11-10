from datetime import UTC, date, datetime
from uuid import UUID, uuid4

import pytest

from app.integrations.business_registration import (
    BusinessRegistrationValidationResult,
)
from app.models.business_verification import BusinessVerification
from app.schemas.business_verification import BusinessVerificationCreateRequest
from app.services.business_verification import (
    BusinessVerificationNotFoundError,
    BusinessVerificationService,
)


class FakeBusinessVerificationRepository:
    def __init__(self) -> None:
        self.verifications: list[BusinessVerification] = []

    async def create(
        self,
        verification: BusinessVerification,
    ) -> BusinessVerification:
        verification.id = len(self.verifications) + 1
        verification.created_at = datetime.now(UTC)
        self.verifications.append(verification)
        return verification

    async def get_by_id_and_requester_id(
        self,
        verification_id: int,
        requester_id: UUID,
    ) -> BusinessVerification | None:
        return next(
            (
                item
                for item in self.verifications
                if item.id == verification_id and item.requester_id == requester_id
            ),
            None,
        )


class FakeBusinessRegistrationClient:
    def __init__(self, valid: bool) -> None:
        self.valid = valid

    async def validate(
        self,
        *,
        business_registration_number: str,
        owner_name: str,
        business_start_date: date,
    ) -> BusinessRegistrationValidationResult:
        return BusinessRegistrationValidationResult(
            valid=self.valid,
            message="확인 결과",
        )


def request() -> BusinessVerificationCreateRequest:
    return BusinessVerificationCreateRequest(
        businessRegistrationNumber="123-45-67890",
        ownerName=" 홍길동 ",
        businessStartDate="2026-01-15",
    )


@pytest.mark.parametrize(
    ("valid", "expected_status"),
    [(True, "VERIFIED"), (False, "INVALID")],
)
async def test_creates_verification_result(
    valid: bool,
    expected_status: str,
) -> None:
    requester_id = uuid4()
    repository = FakeBusinessVerificationRepository()
    service = BusinessVerificationService(
        repository,
        FakeBusinessRegistrationClient(valid),
    )

    result = await service.create(requester_id, request())

    assert result.requester_id == requester_id
    assert result.business_registration_number == "1234567890"
    assert result.owner_name == "홍길동"
    assert result.status == expected_status
    assert result.provider_message == "확인 결과"


async def test_result_is_private_to_requester() -> None:
    requester_id = uuid4()
    repository = FakeBusinessVerificationRepository()
    service = BusinessVerificationService(
        repository,
        FakeBusinessRegistrationClient(True),
    )
    verification = await service.create(requester_id, request())

    with pytest.raises(BusinessVerificationNotFoundError):
        await service.get_for_requester(verification.id, uuid4())
