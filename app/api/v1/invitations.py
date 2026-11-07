from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.stores import get_store_service
from app.api.v1.users import get_user_service
from app.core.auth import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.models.invitation import Invitation
from app.models.user import User
from app.repositories.invitation import InvitationRepository
from app.schemas.invitation import (
    InvitationCodeRequest,
    InvitationCreateRequest,
    InvitationListResponse,
    InvitationResponse,
    InvitationShareInfoResponse,
    InvitationStatus,
    InvitationStoreResponse,
    InvitationSummaryResponse,
    InvitationVerificationResponse,
    MembershipResponse,
)
from app.services.invitation import (
    InvitationAlreadyAvailableError,
    InvitationAlreadyJoinedError,
    InvitationCodeGenerationError,
    InvitationInvalidError,
    InvitationLockedError,
    InvitationNotFoundError,
    InvitationRevokedError,
    InvitationService,
)
from app.services.store import StoreNotFoundError, StoreService
from app.services.user import InactiveUserError, UserService

router = APIRouter(tags=["invitations"])


def get_invitation_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> InvitationService:
    return InvitationService(InvitationRepository(session))


async def _active_user(
    service: UserService,
    identity: AuthenticatedUser,
) -> User:
    try:
        return await service.get_or_create(identity)
    except InactiveUserError:
        return _raise_api_error(
            status.HTTP_403_FORBIDDEN,
            "USER_WITHDRAWN",
            "탈퇴한 사용자예요",
        )


def _raise_api_error(
    status_code: int,
    code: str,
    message: str,
) -> User:
    # This helper only exists to keep the active-user dependency typed.
    from fastapi import HTTPException

    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message, "detail": None},
    )


def _error_response(error: Exception) -> JSONResponse:
    if isinstance(error, InvitationInvalidError):
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "INVITE_INVALID",
                "message": "유효하지 않은 코드예요",
                "detail": {"remainingAttempts": error.remaining_attempts},
            },
        )
    if isinstance(error, InvitationAlreadyJoinedError):
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "INVITE_ALREADY_JOINED",
                "message": "이미 들어간 매장이에요",
                "detail": {
                    "storeId": str(error.store_id),
                    "storeName": error.store_name,
                },
            },
        )
    if isinstance(error, InvitationRevokedError):
        return JSONResponse(
            status_code=status.HTTP_410_GONE,
            content={
                "code": "INVITE_REVOKED",
                "message": "사장님이 삭제했거나 이미 사용한 코드예요",
                "detail": None,
            },
        )
    if isinstance(error, InvitationLockedError):
        return JSONResponse(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            content={
                "code": "INVITE_LOCKED",
                "message": "5번 틀려서 10분 동안 입력할 수 없어요",
                "detail": {"lockedUntil": error.locked_until.isoformat()},
            },
        )
    raise error


def _invitation_status(invitation: Invitation) -> InvitationStatus:
    if invitation.accepted_at is not None:
        return "USED"
    if invitation.revoked_at is not None:
        return "REVOKED"
    return "AVAILABLE"


def _invitation_summary(invitation: Invitation) -> InvitationSummaryResponse:
    return InvitationSummaryResponse(
        invitation_id=invitation.id,
        store_id=invitation.store_id,
        code=invitation.code,
        staff_name=invitation.staff_name,
        hourly_wage=invitation.hourly_wage,
        created_at=invitation.created_at,
        status=_invitation_status(invitation),
        accepted_at=invitation.accepted_at,
        revoked_at=invitation.revoked_at,
    )


@router.post(
    "/stores/{store_id}/invitations",
    response_model=InvitationResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_invitation(
    store_id: UUID,
    request: InvitationCreateRequest,
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    store_service: Annotated[StoreService, Depends(get_store_service)],
    invitation_service: Annotated[
        InvitationService,
        Depends(get_invitation_service),
    ],
) -> InvitationResponse | Response:
    owner = await _active_user(user_service, identity)
    try:
        store = await store_service.get_for_owner(store_id, owner.id)
    except StoreNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "STORE_NOT_FOUND",
                "message": "매장을 찾을 수 없어요",
                "detail": None,
            },
        )
    try:
        invitation = await invitation_service.create(store, owner.id, request)
    except InvitationAlreadyAvailableError as error:
        return JSONResponse(
            status_code=status.HTTP_409_CONFLICT,
            content={
                "code": "INVITE_ALREADY_AVAILABLE",
                "message": "해당 직원에게 이미 사용 가능한 초대 코드가 있어요",
                "detail": {
                    "invitationId": str(error.invitation.id),
                    "code": error.invitation.code,
                },
            },
        )
    except InvitationCodeGenerationError:
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "code": "INVITE_CODE_UNAVAILABLE",
                "message": "초대 코드를 만들지 못했어요. 잠시 후 다시 시도해 주세요",
                "detail": None,
            },
        )
    return InvitationResponse(
        invitation_id=invitation.id,
        store_id=invitation.store_id,
        code=invitation.code,
        staff_name=invitation.staff_name,
        hourly_wage=invitation.hourly_wage,
        created_at=invitation.created_at,
    )


@router.get(
    "/stores/{store_id}/invitations",
    response_model=InvitationListResponse,
)
async def list_invitations(
    store_id: UUID,
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    store_service: Annotated[StoreService, Depends(get_store_service)],
    invitation_service: Annotated[
        InvitationService,
        Depends(get_invitation_service),
    ],
) -> InvitationListResponse | Response:
    owner = await _active_user(user_service, identity)
    try:
        await store_service.get_for_owner(store_id, owner.id)
    except StoreNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "STORE_NOT_FOUND",
                "message": "매장을 찾을 수 없어요",
                "detail": None,
            },
        )
    invitations = await invitation_service.list_for_store(store_id)
    return InvitationListResponse(
        invitations=[_invitation_summary(item) for item in invitations]
    )


@router.get(
    "/stores/{store_id}/invitations/{invitation_id}/share-info",
    response_model=InvitationShareInfoResponse,
)
async def get_invitation_share_info(
    store_id: UUID,
    invitation_id: UUID,
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    store_service: Annotated[StoreService, Depends(get_store_service)],
    invitation_service: Annotated[
        InvitationService,
        Depends(get_invitation_service),
    ],
) -> InvitationShareInfoResponse | Response:
    owner = await _active_user(user_service, identity)
    try:
        await store_service.get_for_owner(store_id, owner.id)
    except StoreNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "STORE_NOT_FOUND",
                "message": "매장을 찾을 수 없어요",
                "detail": None,
            },
        )
    try:
        invitation = await invitation_service.get_shareable(
            store_id,
            invitation_id,
        )
    except InvitationNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "INVITE_NOT_FOUND",
                "message": "초대 코드를 찾을 수 없어요",
                "detail": None,
            },
        )
    except InvitationRevokedError as error:
        return _error_response(error)
    return InvitationShareInfoResponse(
        invitation_id=invitation.id,
        code=invitation.code,
        deep_link=f"/staff/join?code={invitation.code}",
    )


@router.post(
    "/invitations/verify",
    response_model=InvitationVerificationResponse,
)
async def verify_invitation(
    request: InvitationCodeRequest,
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    invitation_service: Annotated[
        InvitationService,
        Depends(get_invitation_service),
    ],
) -> InvitationVerificationResponse | Response:
    user = await _active_user(user_service, identity)
    try:
        verified = await invitation_service.verify(request.code, user.id)
    except (
        InvitationInvalidError,
        InvitationAlreadyJoinedError,
        InvitationRevokedError,
        InvitationLockedError,
    ) as error:
        return _error_response(error)

    return InvitationVerificationResponse(
        code=verified.invitation.code,
        staff_name=verified.invitation.staff_name,
        store=InvitationStoreResponse(
            store_id=verified.store.id,
            name=verified.store.name,
            owner_name=verified.owner.nickname,
            photo_url=verified.store.photo_url,
            theme=None,
        ),
    )


@router.post(
    "/memberships/join",
    response_model=MembershipResponse,
    status_code=status.HTTP_201_CREATED,
)
async def join_membership(
    request: InvitationCodeRequest,
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    invitation_service: Annotated[
        InvitationService,
        Depends(get_invitation_service),
    ],
) -> MembershipResponse | Response:
    user = await _active_user(user_service, identity)
    try:
        membership, store = await invitation_service.join(request.code, user.id)
    except (
        InvitationInvalidError,
        InvitationAlreadyJoinedError,
        InvitationRevokedError,
        InvitationLockedError,
    ) as error:
        return _error_response(error)

    return MembershipResponse(
        store_id=store.id,
        store_name=store.name,
        member_id=membership.id,
        role=membership.role,
        staff_name=membership.staff_name,
        joined_at=membership.joined_at,
    )


@router.delete(
    "/stores/{store_id}/invitations/{invitation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def revoke_invitation(
    store_id: UUID,
    invitation_id: UUID,
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    store_service: Annotated[StoreService, Depends(get_store_service)],
    invitation_service: Annotated[
        InvitationService,
        Depends(get_invitation_service),
    ],
) -> Response:
    owner = await _active_user(user_service, identity)
    try:
        await store_service.get_for_owner(store_id, owner.id)
    except StoreNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "STORE_NOT_FOUND",
                "message": "매장을 찾을 수 없어요",
                "detail": None,
            },
        )
    try:
        await invitation_service.revoke(store_id, invitation_id)
    except InvitationNotFoundError:
        return JSONResponse(
            status_code=status.HTTP_404_NOT_FOUND,
            content={
                "code": "INVITE_NOT_FOUND",
                "message": "초대 코드를 찾을 수 없어요",
                "detail": None,
            },
        )
    except InvitationRevokedError as error:
        return _error_response(error)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
