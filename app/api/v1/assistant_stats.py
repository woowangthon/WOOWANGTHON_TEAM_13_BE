from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.assistant_stats import AssistantStatsRepository
from app.repositories.membership import MembershipRepository
from app.repositories.store import StoreRepository
from app.schemas.assistant_stats import (
    AssistantStatsResponse,
    UnansweredGroup,
    UnansweredQuestion,
)
from app.services.assistant_stats import AssistantStatsService
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError, StoreAccessService

router = APIRouter(
    prefix="/stores/{store_id}/assistant-stats", tags=["assistant-stats"]
)


def get_assistant_stats_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AssistantStatsService:
    return AssistantStatsService(
        AssistantStatsRepository(session),
        StoreAccessService(StoreRepository(session), MembershipRepository(session)),
    )


@router.get("", response_model=AssistantStatsResponse)
async def get_assistant_stats(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AssistantStatsService, Depends(get_assistant_stats_service)],
    week: Annotated[
        date | None,
        Query(description="한국 시간 기준 날짜. 해당 주 월요일로 보정합니다."),
    ] = None,
) -> AssistantStatsResponse:
    """사장님 전용 주간 AI 사수 답변 통계를 조회합니다."""
    try:
        stats = await service.get_stats(store_id, user.id, week)
    except StoreAccessForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner permission required",
        ) from None
    except StoreNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        ) from None
    questions = [
        UnansweredQuestion(
            question_id=question.question_id,
            question=question.question,
            staff_name=question.staff_name,
        )
        for question in stats.questions
    ]
    return AssistantStatsResponse(
        week_start=stats.week_start,
        total=stats.total,
        answered=stats.answered,
        last_week_rate=stats.last_week_rate,
        unanswered=[UnansweredGroup(category="기타", questions=questions)]
        if questions
        else [],
    )
