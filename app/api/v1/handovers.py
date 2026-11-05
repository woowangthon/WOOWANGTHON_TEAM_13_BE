from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user, get_llm_client
from app.db.session import get_db
from app.integrations.llm import LLMClient, LLMError
from app.models.handover import HandoverItem, HandoverNote
from app.models.user import User
from app.repositories.handover import HandoverRepository
from app.repositories.store import StoreRepository
from app.schemas.handover import (
    HandoverConfirmationRequest,
    HandoverDraftRequest,
    HandoverDraftResponse,
    HandoverItemInput,
    HandoverItemResponse,
    HandoverNoteCreateRequest,
    HandoverNoteListResponse,
    HandoverNoteResponse,
    HandoverNoteUpdateRequest,
    HandoverUser,
)
from app.services.handover import (
    HandoverForbiddenError,
    HandoverItemNotFoundError,
    HandoverNoteNotFoundError,
    HandoverService,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessService

router = APIRouter(prefix="/stores/{store_id}", tags=["handovers"])


def get_handover_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> HandoverService:
    """요청에 사용할 인수인계 서비스를 생성합니다."""
    return HandoverService(
        HandoverRepository(session),
        StoreAccessService(StoreRepository(session)),
        llm,
    )


def _to_user(user: User) -> HandoverUser:
    """사용자 모델을 인수인계 응답 형식으로 변환합니다."""
    return HandoverUser(user_id=user.id, name=user.nickname)


def _to_item(item: HandoverItem) -> HandoverItemResponse:
    """항목 모델을 API 응답 형식으로 변환합니다."""
    return HandoverItemResponse(
        item_id=item.id,
        tag=item.tag,
        text=item.text,
        checked=item.checked,
        checked_by=_to_user(item.checked_by) if item.checked_by else None,
        checked_at=item.checked_at,
    )


def _to_response(note: HandoverNote) -> HandoverNoteResponse:
    """노트 모델을 API 응답 형식으로 변환합니다."""
    return HandoverNoteResponse(
        note_id=note.id,
        author=_to_user(note.author),
        created_at=note.created_at,
        updated_at=note.updated_at,
        raw_text=note.raw_text,
        no_issue=note.no_issue,
        summary=note.summary,
        items=[_to_item(item) for item in note.items],
    )


@contextmanager
def _translate_errors() -> Iterator[None]:
    """인수인계 도메인 예외를 HTTP 오류로 변환합니다."""
    try:
        yield
    except StoreNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        ) from None
    except HandoverNoteNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Handover note not found",
        ) from None
    except HandoverItemNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Handover item not found",
        ) from None
    except HandoverForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only the author or owner can change this note",
        ) from None
    except LLMError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is unavailable",
        ) from None


@router.post("/handover-drafts", response_model=HandoverDraftResponse)
async def create_handover_draft(
    store_id: UUID,
    request: HandoverDraftRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[HandoverService, Depends(get_handover_service)],
) -> HandoverDraftResponse:
    """줄글을 저장하지 않고 AI 체크리스트 초안으로 정리합니다."""
    with _translate_errors():
        draft = await service.create_draft(store_id, user.id, request.text)
    return HandoverDraftResponse(
        summary=draft.summary,
        items=[HandoverItemInput.model_validate(item) for item in draft.items],
    )


@router.post(
    "/handover-notes",
    response_model=HandoverNoteResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_handover_note(
    store_id: UUID,
    request: HandoverNoteCreateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[HandoverService, Depends(get_handover_service)],
) -> HandoverNoteResponse:
    """사용자가 확인한 인수인계를 등록합니다."""
    with _translate_errors():
        note = await service.create(store_id, user.id, request)
    return _to_response(note)


@router.get("/handover-notes", response_model=HandoverNoteListResponse)
async def list_handover_notes(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[HandoverService, Depends(get_handover_service)],
    work_date: Annotated[date | None, Query(alias="date")] = None,
) -> HandoverNoteListResponse:
    """날짜별 인수인계 목록을 조회합니다."""
    with _translate_errors():
        target, notes = await service.list_by_date(store_id, user.id, work_date)
    return HandoverNoteListResponse(
        date=target,
        notes=[_to_response(note) for note in notes],
    )


@router.get("/handover-notes/{note_id}", response_model=HandoverNoteResponse)
async def get_handover_note(
    store_id: UUID,
    note_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[HandoverService, Depends(get_handover_service)],
) -> HandoverNoteResponse:
    """인수인계 상세 정보를 조회합니다."""
    with _translate_errors():
        note = await service.get(store_id, note_id, user.id)
    return _to_response(note)


@router.patch("/handover-notes/{note_id}", response_model=HandoverNoteResponse)
async def update_handover_note(
    store_id: UUID,
    note_id: UUID,
    request: HandoverNoteUpdateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[HandoverService, Depends(get_handover_service)],
) -> HandoverNoteResponse:
    """인수인계를 수정합니다."""
    with _translate_errors():
        note = await service.update(store_id, note_id, user.id, request)
    return _to_response(note)


@router.delete(
    "/handover-notes/{note_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_handover_note(
    store_id: UUID,
    note_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[HandoverService, Depends(get_handover_service)],
) -> Response:
    """인수인계를 삭제 처리합니다."""
    with _translate_errors():
        await service.delete(store_id, note_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/handover-notes/{note_id}/confirmations",
    response_model=HandoverNoteResponse,
)
async def confirm_handover_note(
    store_id: UUID,
    note_id: UUID,
    request: HandoverConfirmationRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[HandoverService, Depends(get_handover_service)],
) -> HandoverNoteResponse:
    """항목 하나 또는 노트 전체의 처리 여부를 바꿉니다."""
    with _translate_errors():
        note = await service.confirm(store_id, note_id, user.id, request)
    return _to_response(note)
