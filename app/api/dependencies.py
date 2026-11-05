from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.api.v1.users import get_user_service
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.user import User
from app.services.user import InactiveUserError, UserService


async def get_active_user(
    identity: Annotated[AuthenticatedUser, Depends(get_current_user)],
    service: Annotated[UserService, Depends(get_user_service)],
) -> User:
    """현재 활성 서비스 사용자를 조회하거나 생성합니다."""
    try:
        return await service.get_or_create(identity)
    except InactiveUserError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Withdrawn user account",
        ) from None
