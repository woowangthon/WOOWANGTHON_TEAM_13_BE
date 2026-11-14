from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.assistant_chat import AssistantChat, AssistantMessage
from app.models.membership import Membership
from app.models.user import User
from app.services.assistant_stats import UnansweredQuestionView


class AssistantStatsRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _messages(store_id: UUID, start: datetime, end: datetime) -> Select:
        """삭제되지 않은 매장의 AI 메시지를 반열린 기간으로 제한합니다."""
        return (
            select(AssistantMessage)
            .join(AssistantChat, AssistantChat.id == AssistantMessage.chat_id)
            .where(
                AssistantChat.store_id == store_id,
                AssistantChat.deleted_at.is_(None),
                AssistantMessage.sender == "ai",
                AssistantMessage.created_at >= start,
                AssistantMessage.created_at < end,
            )
        )

    async def count_answers(
        self,
        store_id: UUID,
        start: datetime,
        end: datetime,
    ) -> tuple[int, int]:
        """매장 질문의 전체 수와 답변 수를 DB에서 집계합니다."""
        query = (
            self._messages(store_id, start, end)
            .where(
                AssistantMessage.answer_type.in_(("answered", "not_found")),
            )
            .with_only_columns(
                func.count(AssistantMessage.id),
                func.count(AssistantMessage.id).filter(
                    AssistantMessage.answer_type == "answered",
                ),
            )
        )
        result = await self._session.execute(query)
        total, answered = result.one()
        return total, answered

    async def list_unanswered(
        self,
        store_id: UUID,
        start: datetime,
        end: datetime,
        limit: int,
    ) -> list[UnansweredQuestionView]:
        """미답변마다 직전 직원 질문과 매장 내 이름을 한 쿼리로 조회합니다."""
        staff_message = aliased(AssistantMessage)
        question = (
            select(staff_message.text)
            .where(
                staff_message.chat_id == AssistantMessage.chat_id,
                staff_message.sender == "staff",
                staff_message.created_at < AssistantMessage.created_at,
            )
            .order_by(staff_message.created_at.desc(), staff_message.id.desc())
            .limit(1)
            .correlate(AssistantMessage)
            .scalar_subquery()
        )
        query = (
            self._messages(store_id, start, end)
            .join(User, User.id == AssistantChat.user_id)
            .outerjoin(
                Membership,
                (Membership.store_id == AssistantChat.store_id)
                & (Membership.user_id == AssistantChat.user_id),
            )
            .where(AssistantMessage.answer_type == "not_found")
            .with_only_columns(
                AssistantMessage.id,
                # 이전 질문이 없는 비정상 기록도 미답변 하나로 유지합니다.
                func.coalesce(question, ""),
                func.coalesce(Membership.staff_name, User.nickname),
            )
            .order_by(AssistantMessage.created_at.desc(), AssistantMessage.id.desc())
            .limit(limit)
        )
        result = await self._session.execute(query)
        return [UnansweredQuestionView(*row) for row in result.all()]
