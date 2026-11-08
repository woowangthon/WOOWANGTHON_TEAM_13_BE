from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant_chat import AssistantChat, AssistantMessage


class AssistantChatRepository:
    def __init__(self, session: AsyncSession) -> None:
        """AI 사수 데이터 접근에 사용할 DB 세션을 받습니다."""
        self._session = session

    async def _commit(self) -> None:
        """변경 내용을 저장하고 실패하면 되돌립니다."""
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise

    async def release(self) -> None:
        """외부 호출 전에 열린 트랜잭션을 끝냅니다."""
        await self._commit()

    async def save_chat(self, chat: AssistantChat) -> AssistantChat:
        """채팅방을 저장합니다."""
        self._session.add(chat)
        await self._commit()
        await self._session.refresh(chat)
        return chat

    async def list_chats(self, store_id: UUID, user_id: UUID) -> list[AssistantChat]:
        """사용자의 매장 채팅방을 최근 대화 순으로 조회합니다."""
        query = (
            select(AssistantChat)
            .where(
                AssistantChat.store_id == store_id,
                AssistantChat.user_id == user_id,
                AssistantChat.deleted_at.is_(None),
            )
            .order_by(AssistantChat.last_message_at.desc(), AssistantChat.id)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_chat(
        self,
        chat_id: UUID,
        store_id: UUID,
        user_id: UUID,
    ) -> AssistantChat | None:
        """사용자의 매장 채팅방을 조회합니다."""
        query = select(AssistantChat).where(
            AssistantChat.id == chat_id,
            AssistantChat.store_id == store_id,
            AssistantChat.user_id == user_id,
            AssistantChat.deleted_at.is_(None),
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_message(
        self,
        message_id: UUID,
        chat_id: UUID,
    ) -> AssistantMessage | None:
        """채팅방에 속한 메시지를 조회합니다."""
        query = select(AssistantMessage).where(
            AssistantMessage.id == message_id,
            AssistantMessage.chat_id == chat_id,
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_previous_staff_message(
        self,
        message: AssistantMessage,
    ) -> AssistantMessage | None:
        """AI 답변 직전에 알바생이 보낸 질문 메시지를 조회합니다."""
        query = (
            select(AssistantMessage)
            .where(
                AssistantMessage.chat_id == message.chat_id,
                AssistantMessage.sender == "staff",
                AssistantMessage.created_at <= message.created_at,
                AssistantMessage.id != message.id,
            )
            .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
            .limit(1)
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list_messages(
        self,
        chat_id: UUID,
        before: AssistantMessage | None,
        limit: int,
    ) -> list[AssistantMessage]:
        """기준 메시지 이전의 메시지를 최신 순으로 조회합니다."""
        query = select(AssistantMessage).where(AssistantMessage.chat_id == chat_id)
        if before is not None:
            query = query.where(AssistantMessage.created_at < before.created_at)
        query = query.order_by(
            AssistantMessage.created_at.desc(),
            AssistantMessage.id.desc(),
        ).limit(limit)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def save_exchange(
        self,
        chat: AssistantChat,
        question: AssistantMessage,
        answer: AssistantMessage,
    ) -> None:
        """질문, 답변, 채팅방 요약을 한 번에 저장합니다."""
        self._session.add_all([chat, question, answer])
        await self._commit()
