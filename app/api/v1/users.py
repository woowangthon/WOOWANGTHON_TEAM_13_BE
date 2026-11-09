from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.auth import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.membership import MembershipRepository
from app.repositories.user import UserRepository
from app.schemas.user import (
    MyStoreListResponse,
    StoreSummary,
    UserResponse,
    UserUpdateRequest,
)
from app.services.membership import MembershipService
from app.services.user import InactiveUserError, UserService

router = APIRouter(prefix="/users", tags=["users"])


def get_user_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> UserService:
    """요청에 사용할 사용자 서비스를 생성합니다."""
    return UserService(UserRepository(session))


def get_membership_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> MembershipService:
    """요청에 사용할 멤버십 서비스를 생성합니다."""
    return MembershipService(MembershipRepository(session))


def _to_response(user: User, stores: list[StoreSummary]) -> UserResponse:
    """사용자 모델을 API 응답 형식으로 변환합니다."""
    return UserResponse(
        user_id=user.id,
        nickname=user.nickname,
        email=user.email,
        provider=user.provider,
        stores=stores,
    )


async def _get_or_create_active_user(
    service: UserService,
    identity: AuthenticatedUser,
) -> User:
    """활성 사용자를 조회하고 없으면 생성합니다."""
    try:
        return await service.get_or_create(identity)
    except InactiveUserError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Withdrawn user account",
        ) from None


@router.get("/me", response_model=UserResponse)
async def get_my_profile(
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
    membership_service: Annotated[
        MembershipService,
        Depends(get_membership_service),
    ],
) -> UserResponse:
    """현재 로그인한 사용자의 정보를 조회합니다."""
    user = await _get_or_create_active_user(service, identity)
    stores = await membership_service.list_store_summaries(user.id)
    return _to_response(user, stores)


@router.patch("/me", response_model=UserResponse)
async def update_my_profile(
    request: UserUpdateRequest,
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
    membership_service: Annotated[
        MembershipService,
        Depends(get_membership_service),
    ],
) -> UserResponse:
    """현재 로그인한 사용자의 닉네임을 수정합니다."""
    try:
        user = await service.update_nickname(identity, request.nickname)
    except InactiveUserError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Withdrawn user account",
        ) from None
    stores = await membership_service.list_store_summaries(user.id)
    return _to_response(user, stores)


@router.delete("/me", status_code=status.HTTP_204_NO_CONTENT)
async def withdraw_my_account(
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> Response:
    """현재 로그인한 사용자를 탈퇴 처리합니다."""
    await service.withdraw(identity)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/me/stores", response_model=MyStoreListResponse)
async def get_my_stores(
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
    membership_service: Annotated[
        MembershipService,
        Depends(get_membership_service),
    ],
) -> MyStoreListResponse:
    """현재 사용자가 소속된 매장 목록을 조회합니다."""
    user = await _get_or_create_active_user(service, identity)
    stores = await membership_service.list_store_details(user.id)
    return MyStoreListResponse(stores=stores)
