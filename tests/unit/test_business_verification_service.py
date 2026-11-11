from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.integrations.business_registration import (
    BusinessRegistrationStatusResult,
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
        self.calls = 0

    async def check_status(
        self,
        *,
        business_registration_number: str,
    ) -> BusinessRegistrationStatusResult:
        self.calls += 1
        return BusinessRegistrationStatusResult(
            active=self.valid,
            message="확인 결과",
        )


def request() -> BusinessVerificationCreateRequest:
    return BusinessVerificationCreateRequest(
        businessRegistrationNumber="123-45-67890",
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
    assert result.owner_name is None
    assert result.business_start_date is None
    assert result.status == expected_status
    assert result.provider_message == "확인 결과"


async def test_demo_number_is_verified_without_provider_call() -> None:
    requester_id = uuid4()
    repository = FakeBusinessVerificationRepository()
    client = FakeBusinessRegistrationClient(False)
    service = BusinessVerificationService(repository, client)

    result = await service.create(
        requester_id,
        BusinessVerificationCreateRequest(businessRegistrationNumber="000-00-00000"),
    )

    assert result.status == "VERIFIED"
    assert result.provider_message == "시연·테스트용 사업자등록번호입니다."
    assert client.calls == 0


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
