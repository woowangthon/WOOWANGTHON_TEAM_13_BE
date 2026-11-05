from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user
from app.core.config import settings
from app.db.session import get_db
from app.integrations.gemini import GeminiClient
from app.integrations.llm import LLMError
from app.models.assistant_chat import AssistantChat, AssistantMessage
from app.models.user import User
from app.repositories.assistant_chat import AssistantChatRepository
from app.repositories.manual import ManualRepository
from app.repositories.recipe import RecipeRepository
from app.repositories.store import StoreRepository
from app.schemas.assistant_chat import (
    AssistantChatDetailResponse,
    AssistantChatListResponse,
    AssistantChatSummary,
    AssistantExchangeResponse,
    AssistantMessageCreateRequest,
    AssistantMessageListResponse,
    AssistantMessageResponse,
    AssistantSource,
)
from app.services.assistant_chat import (
    AssistantChatNotFoundError,
    AssistantChatService,
    AssistantMessageNotFoundError,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessService

router = APIRouter(
    prefix="/stores/{store_id}/assistant-chats",
    tags=["assistant-chats"],
)


def get_assistant_chat_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AssistantChatService:
    """요청에 사용할 AI 사수 서비스를 생성합니다."""
    return AssistantChatService(
        AssistantChatRepository(session),
        ManualRepository(session),
        RecipeRepository(session),
        StoreAccessService(StoreRepository(session)),
        GeminiClient(
            api_key=settings.gemini_api_key,
            model=settings.gemini_model,
            timeout_seconds=settings.llm_timeout_seconds,
        ),
    )


def _to_summary(chat: AssistantChat) -> AssistantChatSummary:
    """채팅방 모델을 목록 항목 형식으로 변환합니다."""
    return AssistantChatSummary(
        chat_id=chat.id,
        store_id=chat.store_id,
        created_at=chat.created_at,
        last_message_at=chat.last_message_at,
        last_message_text=chat.last_message_text,
    )


def _to_message(message: AssistantMessage) -> AssistantMessageResponse:
    """메시지 모델을 API 응답 형식으로 변환합니다."""
    return AssistantMessageResponse(
        message_id=message.id,
        sender=message.sender,
        text=message.text,
        answer_type=message.answer_type,
        sources=[AssistantSource(**source) for source in message.sources],
        # TODO: 사장님께 물어보기 API가 생기면 not_found 답변에서 true로 내려줍니다.
        can_ask_owner=False,
        owner_question=None,
        created_at=message.created_at,
    )


@contextmanager
def _translate_errors() -> Iterator[None]:
    """AI 사수 도메인 예외를 HTTP 오류로 변환합니다."""
    try:
        yield
    except StoreNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        ) from None
    except AssistantChatNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assistant chat not found",
        ) from None
    except AssistantMessageNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Assistant message not found",
        ) from None
    except LLMError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is unavailable",
        ) from None


@router.post(
    "",
    response_model=AssistantChatDetailResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_assistant_chat(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AssistantChatService, Depends(get_assistant_chat_service)],
) -> AssistantChatDetailResponse:
    """AI 사수 채팅방을 생성합니다."""
    with _translate_errors():
        chat, suggestions = await service.create_chat(store_id, user.id)
    return AssistantChatDetailResponse(
        **_to_summary(chat).model_dump(by_alias=False),
        suggestions=suggestions,
        messages=[],
    )


@router.get("", response_model=AssistantChatListResponse)
async def list_assistant_chats(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AssistantChatService, Depends(get_assistant_chat_service)],
) -> AssistantChatListResponse:
    """내 AI 사수 채팅방 목록을 조회합니다."""
    with _translate_errors():
        chats, suggestions = await service.list_chats(store_id, user.id)
    return AssistantChatListResponse(
        suggestions=suggestions,
        chats=[_to_summary(chat) for chat in chats],
    )


@router.delete("/{chat_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_assistant_chat(
    store_id: UUID,
    chat_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AssistantChatService, Depends(get_assistant_chat_service)],
) -> Response:
    """내 AI 사수 채팅방을 삭제 처리합니다."""
    with _translate_errors():
        await service.delete_chat(store_id, chat_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{chat_id}/messages",
    response_model=AssistantExchangeResponse,
    status_code=status.HTTP_201_CREATED,
)
async def send_assistant_message(
    store_id: UUID,
    chat_id: UUID,
    request: AssistantMessageCreateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AssistantChatService, Depends(get_assistant_chat_service)],
) -> AssistantExchangeResponse:
    """질문을 보내고 매장 문서에 근거한 AI 답변을 받습니다."""
    with _translate_errors():
        question, answer = await service.send_message(
            store_id,
            chat_id,
            user.id,
            request.text,
        )
    return AssistantExchangeResponse(
        question=_to_message(question),
        answer=_to_message(answer),
    )


@router.get("/{chat_id}/messages", response_model=AssistantMessageListResponse)
async def list_assistant_messages(
    store_id: UUID,
    chat_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AssistantChatService, Depends(get_assistant_chat_service)],
    before: UUID | None = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> AssistantMessageListResponse:
    """채팅방의 메시지 내역을 오래된 순으로 조회합니다."""
    with _translate_errors():
        messages, has_more = await service.list_messages(
            store_id,
            chat_id,
            user.id,
            before,
            limit,
        )
    return AssistantMessageListResponse(
        chat_id=chat_id,
        has_more=has_more,
        messages=[_to_message(message) for message in messages],
    )
