from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, Literal
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse

from app.api.dependencies import get_active_user
from app.api.v1.assistant_chats import get_owner_question_service
from app.integrations.llm import LLMError
from app.models.user import User
from app.schemas.owner_question import (
    ManualDraftRequest,
    ManualDraftResponse,
    OwnerQuestionAnswerRequest,
    OwnerQuestionAnswerResponse,
    OwnerQuestionItem,
    OwnerQuestionListResponse,
)
from app.services.manual import ManualCategoryNotFoundError
from app.services.owner_question import (
    ManualDraft,
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
    except ManualCategoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Manual category not found",
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
    response_model=OwnerQuestionAnswerResponse,
    responses={
        status.HTTP_409_CONFLICT: {
            "description": "OWNER_QUESTION_ALREADY_ANSWERED",
        },
    },
)
async def answer_owner_question(
    store_id: UUID,
    question_id: UUID,
    request: OwnerQuestionAnswerRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[OwnerQuestionService, Depends(get_owner_question_service)],
) -> OwnerQuestionAnswerResponse | JSONResponse:
    """사장님 답변을 저장하고, 요청하면 매뉴얼로도 추가합니다."""
    draft = None
    if request.add_to_manual:
        draft = ManualDraft(
            title=request.manual_title,
            body=request.manual_body,
            category_id=request.manual_category_id,
        )
    try:
        with _translate_errors():
            view = await service.answer(
                store_id,
                question_id,
                user.id,
                request.answer,
                draft,
            )
    except OwnerQuestionAlreadyAnsweredError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "OWNER_QUESTION_ALREADY_ANSWERED",
            "이미 답변한 질문이에요",
        )
    item = _to_item(view)
    return OwnerQuestionAnswerResponse(
        **item.model_dump(),
        manual_id=view.manual_id,
    )


@router.post(
    "/{question_id}/manual-draft",
    response_model=ManualDraftResponse,
    responses={
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "AI_UNAVAILABLE"},
    },
)
async def draft_manual_from_answer(
    store_id: UUID,
    question_id: UUID,
    request: ManualDraftRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[OwnerQuestionService, Depends(get_owner_question_service)],
) -> ManualDraftResponse | JSONResponse:
    """질문과 사장님 답변을 AI로 매뉴얼 초안으로 정리합니다. 저장하지 않습니다."""
    try:
        with _translate_errors():
            draft = await service.manual_draft(
                store_id,
                question_id,
                user.id,
                request.answer,
            )
    except LLMError:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "AI_UNAVAILABLE",
            "AI가 정리하지 못했어요. 직접 작성하거나 잠시 후 다시 시도해 주세요",
        )
    return ManualDraftResponse(title=draft.title or "", body=draft.body or "")
