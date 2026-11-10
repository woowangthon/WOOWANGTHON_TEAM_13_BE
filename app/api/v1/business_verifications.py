from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user
from app.core.config import settings
from app.db.session import get_db
from app.integrations.business_registration import (
    BusinessRegistrationAPIError,
    BusinessRegistrationConfigurationError,
    NTSBusinessRegistrationClient,
)
from app.models.business_verification import BusinessVerification
from app.models.user import User
from app.repositories.business_verification import BusinessVerificationRepository
from app.schemas.business_verification import (
    BusinessVerificationCreateRequest,
    BusinessVerificationResponse,
)
from app.services.business_verification import (
    BusinessVerificationNotFoundError,
    BusinessVerificationService,
)

router = APIRouter(
    prefix="/stores/business-verifications",
    tags=["business-verifications"],
)


def get_business_verification_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> BusinessVerificationService:
    return BusinessVerificationService(
        BusinessVerificationRepository(session),
        NTSBusinessRegistrationClient(
            api_key=settings.nts_business_api_key,
        ),
    )


def _to_response(
    verification: BusinessVerification,
) -> BusinessVerificationResponse:
    return BusinessVerificationResponse(
        verification_id=verification.id,
        business_registration_number=verification.business_registration_number,
        owner_name=verification.owner_name,
        business_start_date=verification.business_start_date,
        status=verification.status,
        message=verification.provider_message,
        created_at=verification.created_at,
    )


@router.post(
    "",
    response_model=BusinessVerificationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_business_verification(
    request: BusinessVerificationCreateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[
        BusinessVerificationService,
        Depends(get_business_verification_service),
    ],
) -> BusinessVerificationResponse:
    try:
        verification = await service.create(user.id, request)
    except BusinessRegistrationConfigurationError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Business verification is not configured",
        ) from None
    except BusinessRegistrationAPIError:
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail="Business verification provider request failed",
        ) from None
    return _to_response(verification)


@router.get(
    "/{verification_id}",
    response_model=BusinessVerificationResponse,
)
async def get_business_verification(
    verification_id: int,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[
        BusinessVerificationService,
        Depends(get_business_verification_service),
    ],
) -> BusinessVerificationResponse:
    try:
        verification = await service.get_for_requester(
            verification_id,
            user.id,
        )
    except BusinessVerificationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Business verification not found",
        ) from None
    return _to_response(verification)
