from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.api.dependencies import get_active_user
from app.api.v1.assistant_chats import get_owner_question_service
from app.models.user import User
from app.schemas.owner_question import (
    OwnerQuestionAnswerRequest,
    OwnerQuestionItem,
    OwnerQuestionListResponse,
)
from app.services.owner_question import (
    AddToManualNotSupportedError,
    OwnerQuestionAlreadyAnsweredError,
    OwnerQuestionNotFoundError,
    OwnerQuestionService,
    OwnerQuestionView,
    question_title,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError

router = APIRouter(
    prefix="/stores/{store_id}/owner-questions",
    tags=["owner-questions"],
)


def _to_item(view: OwnerQuestionView) -> OwnerQuestionItem:
    """질문을 사장님 화면의 목록 항목 형식으로 변환합니다."""
    question = view.question
    return OwnerQuestionItem(
        question_id=question.id,
        store_id=question.store_id,
        title=question_title(question.question),
        question=question.question,
        icon=None,
        staff_name=view.staff_name,
        asked_at=question.created_at,
        status=question.status,
        answer=question.answer,
        answered_at=question.answered_at,
    )


@contextmanager
def _translate_errors() -> Iterator[None]:
    """권한과 질문 조회 예외를 HTTP 오류로 변환합니다."""
    try:
        yield
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
    except OwnerQuestionNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Owner question not found",
        ) from None


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """FE와 맞춘 code, message 형식의 오류 응답을 만듭니다."""
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "detail": None},
    )


@router.get("", response_model=OwnerQuestionListResponse)
async def list_owner_questions(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[OwnerQuestionService, Depends(get_owner_question_service)],
    status_filter: Annotated[
        Literal["asked", "answered"] | None,
        Query(alias="status"),
    ] = None,
) -> OwnerQuestionListResponse:
    """사장님이 매장에 들어온 질문을 최신 순으로 조회합니다."""
    with _translate_errors():
        views = await service.list_questions(store_id, user.id, status_filter)
    return OwnerQuestionListResponse(questions=[_to_item(view) for view in views])


@router.post(
    "/{question_id}/answer",
    response_model=OwnerQuestionItem,
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "OWNER_QUESTION_ALREADY_ANSWERED",
        },
        status.HTTP_501_NOT_IMPLEMENTED: {"description": "ADD_TO_MANUAL_NOT_SUPPORTED"},
    },
)
async def answer_owner_question(
    store_id: UUID,
    question_id: UUID,
    request: OwnerQuestionAnswerRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[OwnerQuestionService, Depends(get_owner_question_service)],
) -> OwnerQuestionItem | JSONResponse:
    """사장님 답변을 저장하고 알바생 채팅에 전달합니다."""
    try:
        with _translate_errors():
            view = await service.answer(
                store_id,
                question_id,
                user.id,
                request.answer,
                request.add_to_manual,
            )
    except OwnerQuestionAlreadyAnsweredError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "OWNER_QUESTION_ALREADY_ANSWERED",
            "이미 답변한 질문이에요",
        )
    except AddToManualNotSupportedError:
        return _error_response(
            status.HTTP_501_NOT_IMPLEMENTED,
            "ADD_TO_MANUAL_NOT_SUPPORTED",
            "매뉴얼에 추가하기는 아직 지원하지 않아요",
        )
    return _to_item(view)
