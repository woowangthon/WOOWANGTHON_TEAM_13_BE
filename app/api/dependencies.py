from typing import Annotated

from fastapi import Depends, HTTPException, status

from app.api.v1.users import get_user_service
from app.core.auth import AuthenticatedUser, get_current_user
from app.core.config import settings
from app.integrations.gemini import GeminiClient
from app.integrations.llm import LLMClient
from app.models.user import User
from app.services.user import InactiveUserError, UserService


def get_llm_client() -> LLMClient:
    """요청에 사용할 LLM 클라이언트를 생성합니다."""
    return GeminiClient(
        api_key=settings.gemini_api_key,
        model=settings.gemini_model,
        timeout_seconds=settings.llm_timeout_seconds,
    )


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
