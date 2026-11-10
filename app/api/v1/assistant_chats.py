from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user, get_llm_client
from app.db.session import get_db
from app.integrations.llm import LLMClient, LLMError
from app.models.assistant_chat import AssistantChat, AssistantMessage
from app.models.owner_question import OwnerQuestion
from app.models.user import User
from app.repositories.assistant_chat import AssistantChatRepository
from app.repositories.manual import ManualRepository
from app.repositories.membership import MembershipRepository
from app.repositories.owner_question import OwnerQuestionRepository
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
    OwnerQuestionCreateResponse,
    OwnerQuestionRef,
)
from app.services.assistant_chat import (
    NOT_FOUND,
    AssistantChatNotFoundError,
    AssistantChatService,
    AssistantMessageNotFoundError,
)
from app.services.owner_question import (
    OwnerQuestionAlreadySentError,
    OwnerQuestionNotAllowedError,
    OwnerQuestionService,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessService

router = APIRouter(
    prefix="/stores/{store_id}/assistant-chats",
    tags=["assistant-chats"],
)


def get_assistant_chat_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> AssistantChatService:
    """요청에 사용할 AI 사수 서비스를 생성합니다."""
    return AssistantChatService(
        AssistantChatRepository(session),
        ManualRepository(session),
        RecipeRepository(session),
        StoreAccessService(
            StoreRepository(session),
            MembershipRepository(session),
        ),
        llm,
    )


def get_owner_question_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> OwnerQuestionService:
    """요청에 사용할 사장님께 물어보기 서비스를 생성합니다."""
    return OwnerQuestionService(
        AssistantChatRepository(session),
        OwnerQuestionRepository(session),
        StoreAccessService(
            StoreRepository(session),
            MembershipRepository(session),
        ),
        ManualRepository(session),
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


def to_message_response(
    message: AssistantMessage,
    owner_question: OwnerQuestion | None = None,
) -> AssistantMessageResponse:
    """메시지 모델을 API 응답 형식으로 변환합니다."""
    can_ask_owner = (
        message.sender == "ai"
        and message.answer_type == NOT_FOUND
        and owner_question is None
    )
    reference = None
    if owner_question is not None:
        reference = OwnerQuestionRef(
            owner_question_id=owner_question.id,
            status=owner_question.status,
        )
    return AssistantMessageResponse(
        message_id=message.id,
        sender=message.sender,
        text=message.text,
        answer_type=message.answer_type,
        sources=[AssistantSource(**source) for source in message.sources],
        can_ask_owner=can_ask_owner,
        owner_question=reference,
        created_at=message.created_at,
    )


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """FE와 맞춘 code, message 형식의 오류 응답을 만듭니다."""
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "detail": None},
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
        question=to_message_response(question),
        answer=to_message_response(answer),
    )


@router.get("/{chat_id}/messages", response_model=AssistantMessageListResponse)
async def list_assistant_messages(
    store_id: UUID,
    chat_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AssistantChatService, Depends(get_assistant_chat_service)],
    owner_questions: Annotated[
        OwnerQuestionService,
        Depends(get_owner_question_service),
    ],
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
    asked = await owner_questions.questions_for_messages(messages)
    return AssistantMessageListResponse(
        chat_id=chat_id,
        has_more=has_more,
        messages=[
            to_message_response(message, asked.get(message.id))
            for message in messages
        ],
    )


@router.post(
    "/{chat_id}/messages/{message_id}/owner-questions",
    response_model=OwnerQuestionCreateResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_409_CONFLICT: {"description": "OWNER_QUESTION_ALREADY_SENT"},
        status.HTTP_422_UNPROCESSABLE_CONTENT: {
            "description": "OWNER_QUESTION_NOT_ALLOWED",
        },
    },
)
async def ask_owner(
    store_id: UUID,
    chat_id: UUID,
    message_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[OwnerQuestionService, Depends(get_owner_question_service)],
) -> OwnerQuestionCreateResponse | JSONResponse:
    """찾지 못한 AI 답변의 질문을 사장님께 넘깁니다."""
    try:
        with _translate_errors():
            question, system_message = await service.ask(
                store_id,
                chat_id,
                message_id,
                user.id,
            )
    except OwnerQuestionNotAllowedError:
        return _error_response(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "OWNER_QUESTION_NOT_ALLOWED",
            "찾지 못한 답변만 사장님께 물어볼 수 있어요",
        )
    except OwnerQuestionAlreadySentError:
        return _error_response(
            status.HTTP_409_CONFLICT,
            "OWNER_QUESTION_ALREADY_SENT",
            "이미 사장님께 물어봤어요",
        )
    return OwnerQuestionCreateResponse(
        owner_question_id=question.id,
        status=question.status,
        question=question.question,
        created_at=question.created_at,
        system_message=to_message_response(system_message),
    )
