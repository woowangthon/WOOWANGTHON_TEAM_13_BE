from datetime import datetime
from typing import Any, cast
from uuid import UUID

from sqlalchemy import CursorResult, and_, func, select, update
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.assistant_chat import AssistantChat, AssistantMessage
from app.models.membership import Membership
from app.models.owner_question import (
    OWNER_QUESTION_ANSWERED,
    OWNER_QUESTION_ASKED,
    OwnerQuestion,
)
from app.models.user import User


class OwnerQuestionRepository:
    def __init__(self, session: AsyncSession) -> None:
        """사장님께 물어보기 데이터 접근에 사용할 DB 세션을 받습니다."""
        self._session = session

    async def _commit(self) -> None:
        """변경 내용을 저장하고 실패하면 되돌립니다."""
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise

    def _with_staff_name(self) -> Any:
        """질문과 질문한 직원 이름을 함께 고르는 쿼리를 만듭니다."""
        staff_name = func.coalesce(Membership.staff_name, User.nickname)
        return (
            select(OwnerQuestion, staff_name)
            .join(User, User.id == OwnerQuestion.asked_by)
            .outerjoin(
                Membership,
                and_(
                    Membership.store_id == OwnerQuestion.store_id,
                    Membership.user_id == OwnerQuestion.asked_by,
                ),
            )
        )

    async def list_by_message_ids(
        self,
        message_ids: list[UUID],
    ) -> list[OwnerQuestion]:
        """AI 답변 메시지에 연결된 질문을 조회합니다."""
        if not message_ids:
            return []
        query = select(OwnerQuestion).where(OwnerQuestion.message_id.in_(message_ids))
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_by_store_id(
        self,
        store_id: UUID,
        status: str | None,
    ) -> list[tuple[OwnerQuestion, str]]:
        """매장의 질문을 최신 순으로 직원 이름과 함께 조회합니다."""
        query = self._with_staff_name().where(OwnerQuestion.store_id == store_id)
        if status is not None:
            query = query.where(OwnerQuestion.status == status)
        query = query.order_by(OwnerQuestion.created_at.desc(), OwnerQuestion.id)
        result = await self._session.execute(query)
        return [(question, name) for question, name in result.all()]

    async def get_by_id_and_store_id(
        self,
        question_id: UUID,
        store_id: UUID,
    ) -> tuple[OwnerQuestion, str] | None:
        """매장의 질문 하나를 직원 이름과 함께 조회합니다."""
        query = self._with_staff_name().where(
            OwnerQuestion.id == question_id,
            OwnerQuestion.store_id == store_id,
        )
        result = await self._session.execute(query)
        row = result.first()
        if row is None:
            return None
        return row[0], row[1]

    async def get_chat(self, chat_id: UUID) -> AssistantChat | None:
        """질문이 나온 채팅방을 조회합니다."""
        return await self._session.get(AssistantChat, chat_id)

    async def save_asked(
        self,
        question: OwnerQuestion,
        system_message: AssistantMessage,
        chat: AssistantChat,
    ) -> bool:
        """질문과 안내 메시지를 저장하고 이미 물어본 답변이면 False를 반환합니다."""
        self._session.add_all([question, system_message, chat])
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            return False
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        return True

    async def save_answer(
        self,
        question: OwnerQuestion,
        answered_by: UUID,
        answered_at: datetime,
        owner_message: AssistantMessage,
        chat: AssistantChat,
    ) -> bool:
        """답하지 않은 질문에만 답변을 저장하고 이미 답했으면 False를 반환합니다."""
        query = (
            update(OwnerQuestion)
            .where(
                OwnerQuestion.id == question.id,
                OwnerQuestion.status == OWNER_QUESTION_ASKED,
            )
            .values(
                status=OWNER_QUESTION_ANSWERED,
                answer=owner_message.text,
                answered_by=answered_by,
                answered_at=answered_at,
            )
            .execution_options(synchronize_session=False)
        )
        try:
            result = await self._session.execute(query)
            if cast(CursorResult[Any], result).rowcount != 1:
                await self._session.rollback()
                return False
            self._session.add_all([owner_message, chat])
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(question)
        return True
