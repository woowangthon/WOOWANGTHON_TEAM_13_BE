from typing import Protocol
from uuid import UUID

from app.integrations.business_registration import (
    BusinessRegistrationStatusResult,
)
from app.models.business_verification import BusinessVerification
from app.schemas.business_verification import BusinessVerificationCreateRequest

VERIFIED_STATUS = "VERIFIED"
INVALID_STATUS = "INVALID"
DEMO_BUSINESS_REGISTRATION_NUMBER = "0000000000"


class BusinessVerificationNotFoundError(Exception):
    """요청자가 조회할 수 있는 인증 결과가 없습니다."""


class BusinessRegistrationClientProtocol(Protocol):
    async def check_status(
        self,
        *,
        business_registration_number: str,
    ) -> BusinessRegistrationStatusResult: ...


class BusinessVerificationRepositoryProtocol(Protocol):
    async def create(
        self,
        verification: BusinessVerification,
    ) -> BusinessVerification: ...

    async def get_by_id_and_requester_id(
        self,
        verification_id: int,
        requester_id: UUID,
    ) -> BusinessVerification | None: ...


class BusinessVerificationService:
    def __init__(
        self,
        repository: BusinessVerificationRepositoryProtocol,
        client: BusinessRegistrationClientProtocol,
    ) -> None:
        self._repository = repository
        self._client = client

    async def create(
        self,
        requester_id: UUID,
        request: BusinessVerificationCreateRequest,
    ) -> BusinessVerification:
        if request.business_registration_number == DEMO_BUSINESS_REGISTRATION_NUMBER:
            result = BusinessRegistrationStatusResult(
                active=True,
                message="시연·테스트용 사업자등록번호입니다.",
            )
        else:
            result = await self._client.check_status(
                business_registration_number=request.business_registration_number,
            )
        verification = BusinessVerification(
            requester_id=requester_id,
            business_registration_number=request.business_registration_number,
            owner_name=None,
            business_start_date=None,
            status=VERIFIED_STATUS if result.active else INVALID_STATUS,
            provider_message=result.message,
        )
        return await self._repository.create(verification)

    async def get_for_requester(
        self,
        verification_id: int,
        requester_id: UUID,
    ) -> BusinessVerification:
        verification = await self._repository.get_by_id_and_requester_id(
            verification_id,
            requester_id,
        )
        if verification is None:
            raise BusinessVerificationNotFoundError
        return verification
