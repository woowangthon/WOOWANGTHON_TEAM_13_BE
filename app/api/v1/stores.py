from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.v1.users import get_user_service
from app.core.auth import AuthenticatedUser, get_current_user
from app.db.session import get_db
from app.models.store import Store
from app.models.user import User
from app.repositories.store import StoreRepository
from app.schemas.store import (
    BusinessSize,
    StoreCreateRequest,
    StoreListResponse,
    StoreResponse,
    StoreUpdateRequest,
)
from app.services.store import StoreNotFoundError, StoreService
from app.services.user import InactiveUserError, UserService

router = APIRouter(prefix="/stores", tags=["stores"])


def get_store_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StoreService:
    """요청에 사용할 매장 서비스를 생성합니다."""
    return StoreService(StoreRepository(session))


async def _get_active_user(
    service: UserService,
    identity: AuthenticatedUser,
) -> User:
    """현재 활성 서비스 사용자를 조회하거나 생성합니다."""
    try:
        return await service.get_or_create(identity)
    except InactiveUserError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Withdrawn user account",
        ) from None


def _to_response(store: Store, owner_name: str) -> StoreResponse:
    """매장 모델을 API 응답 형식으로 변환합니다."""
    return StoreResponse(
        store_id=store.id,
        name=store.name,
        address=store.address,
        owner_name=owner_name,
        business_verification_id=store.business_verification_id,
        photo_url=store.photo_url,
        payday=store.payday,
        business_size=cast(BusinessSize | None, store.business_size),
    )


async def _get_store_or_404(
    service: StoreService,
    store_id: UUID,
    owner_id: UUID,
) -> Store:
    """소유자의 매장을 조회하고 없으면 404를 반환합니다."""
    try:
        return await service.get_for_owner(store_id, owner_id)
    except StoreNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        ) from None


@router.post("", response_model=StoreResponse, status_code=status.HTTP_201_CREATED)
async def create_store(
    request: StoreCreateRequest,
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    store_service: Annotated[StoreService, Depends(get_store_service)],
) -> StoreResponse:
    """현재 사용자가 소유할 매장을 등록합니다."""
    owner = await _get_active_user(user_service, identity)
    store = await store_service.create(owner.id, request)
    return _to_response(store, owner.nickname)


@router.get("", response_model=StoreListResponse)
async def list_stores(
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    store_service: Annotated[StoreService, Depends(get_store_service)],
) -> StoreListResponse:
    """현재 사용자가 소유한 매장 목록을 조회합니다."""
    owner = await _get_active_user(user_service, identity)
    stores = await store_service.list_for_owner(owner.id)
    return StoreListResponse(
        stores=[_to_response(store, owner.nickname) for store in stores]
    )


@router.get("/{store_id}", response_model=StoreResponse)
async def get_store(
    store_id: UUID,
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    store_service: Annotated[StoreService, Depends(get_store_service)],
) -> StoreResponse:
    """현재 사용자가 소유한 매장 상세 정보를 조회합니다."""
    owner = await _get_active_user(user_service, identity)
    store = await _get_store_or_404(store_service, store_id, owner.id)
    return _to_response(store, owner.nickname)


@router.patch("/{store_id}", response_model=StoreResponse)
async def update_store(
    store_id: UUID,
    request: StoreUpdateRequest,
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    store_service: Annotated[StoreService, Depends(get_store_service)],
) -> StoreResponse:
    """현재 사용자가 소유한 매장 정보를 수정합니다."""
    owner = await _get_active_user(user_service, identity)
    try:
        store = await store_service.update(store_id, owner.id, request)
    except StoreNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        ) from None
    return _to_response(store, owner.nickname)


@router.delete("/{store_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_store(
    store_id: UUID,
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    user_service: Annotated[UserService, Depends(get_user_service)],
    store_service: Annotated[StoreService, Depends(get_store_service)],
) -> Response:
    """현재 사용자가 소유한 매장을 삭제 처리합니다."""
    owner = await _get_active_user(user_service, identity)
    try:
        await store_service.delete(store_id, owner.id)
    except StoreNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
