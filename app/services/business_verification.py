from datetime import date
from typing import Protocol
from uuid import UUID

from app.integrations.business_registration import (
    BusinessRegistrationValidationResult,
)
from app.models.business_verification import BusinessVerification
from app.schemas.business_verification import BusinessVerificationCreateRequest

VERIFIED_STATUS = "VERIFIED"
INVALID_STATUS = "INVALID"


class BusinessVerificationNotFoundError(Exception):
    """요청자가 조회할 수 있는 인증 결과가 없습니다."""


class BusinessRegistrationClientProtocol(Protocol):
    async def validate(
        self,
        *,
        business_registration_number: str,
        owner_name: str,
        business_start_date: date,
    ) -> BusinessRegistrationValidationResult: ...


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
        result = await self._client.validate(
            business_registration_number=request.business_registration_number,
            owner_name=request.owner_name,
            business_start_date=request.business_start_date,
        )
        verification = BusinessVerification(
            requester_id=requester_id,
            business_registration_number=request.business_registration_number,
            owner_name=request.owner_name,
            business_start_date=request.business_start_date,
            status=VERIFIED_STATUS if result.valid else INVALID_STATUS,
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
