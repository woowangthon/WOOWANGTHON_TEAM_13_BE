from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import aliased

from app.models.handover import HandoverItem, HandoverNote
from app.models.membership import Membership
from app.models.notification import NotificationRead, ScheduleChangeNotice
from app.models.owner_question import OWNER_QUESTION_ANSWERED, OwnerQuestion
from app.models.schedule import ScheduleAssignment, ShiftTemplate, SubstituteRequest
from app.models.store import Store
from app.models.user import User
from app.services.notification import (
    AnswerEvent,
    HandoverEvent,
    QuestionEvent,
    ScheduleChangeEvent,
    SubstituteEvent,
    UncheckedItem,
    Viewer,
)

SUBSTITUTE_ACCEPTED_STATUS = "ACCEPTED"
SUBSTITUTE_CANCELLED_STATUS = "CANCELLED"
SUBSTITUTE_REJECTED_STATUS = "REJECTED"


def _aware(value: datetime) -> datetime:
    """시간대 없이 읽힌 시각을 UTC로 봅니다."""
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


class NotificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        """알림을 모으는 데 사용할 DB 세션을 받습니다."""
        self._session = session

    @staticmethod
    def _name_of() -> tuple[Any, Any, Any]:
        """매장 구성원 이름, 없으면 닉네임을 고르는 식과 조인 대상을 만듭니다."""
        user = aliased(User)
        member = aliased(Membership)
        name = func.coalesce(member.staff_name, user.nickname)
        return name, user, member

    async def get_viewer(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> tuple[Viewer, UUID | None] | None:
        """사용자가 매장 사장님인지, 재직 중인 구성원인지 조회합니다."""
        owned = await self._session.execute(
            select(Store.id).where(
                Store.id == store_id,
                Store.owner_id == user_id,
                Store.deleted_at.is_(None),
            )
        )
        if owned.scalar_one_or_none() is not None:
            return "owner", None
        membership = await self._session.execute(
            select(Membership.id)
            .join(Store, Store.id == Membership.store_id)
            .where(
                Membership.store_id == store_id,
                Membership.user_id == user_id,
                Membership.left_at.is_(None),
                Store.deleted_at.is_(None),
            )
        )
        membership_id = membership.scalar_one_or_none()
        if membership_id is None:
            return None
        return "staff", membership_id

    async def _substitutes(
        self,
        store_id: UUID,
        *conditions: Any,
        other_user: Any,
        at: Any,
    ) -> list[SubstituteEvent]:
        """대타 요청을 근무 시간, 상대방 이름과 함께 조회합니다."""
        name, user, member = self._name_of()
        query = (
            select(
                SubstituteRequest.id,
                SubstituteRequest.work_date,
                ShiftTemplate.start_time,
                ShiftTemplate.end_time,
                name,
                at,
            )
            .join(
                ScheduleAssignment,
                ScheduleAssignment.id == SubstituteRequest.schedule_assignment_id,
            )
            .join(ShiftTemplate, ShiftTemplate.id == ScheduleAssignment.template_id)
            .join(user, user.id == other_user)
            .outerjoin(
                member,
                and_(member.store_id == store_id, member.user_id == other_user),
            )
            .where(SubstituteRequest.store_id == store_id, *conditions)
        )
        rows = (await self._session.execute(query)).all()
        return [SubstituteEvent(*row) for row in rows]

    async def list_received_substitutes(
        self,
        store_id: UUID,
        user_id: UUID,
        since: datetime,
    ) -> list[SubstituteEvent]:
        """내가 받은 대타 요청을 조회합니다. 취소된 요청은 뺍니다."""
        return await self._substitutes(
            store_id,
            SubstituteRequest.target_user_id == user_id,
            SubstituteRequest.status != SUBSTITUTE_CANCELLED_STATUS,
            SubstituteRequest.created_at >= since,
            other_user=SubstituteRequest.requester_user_id,
            at=SubstituteRequest.created_at,
        )

    async def list_accepted_substitutes(
        self,
        store_id: UUID,
        user_id: UUID,
        since: datetime,
    ) -> list[SubstituteEvent]:
        """내가 보낸 대타 요청 중 상대가 수락한 것을 조회합니다."""
        return await self._substitutes(
            store_id,
            SubstituteRequest.requester_user_id == user_id,
            SubstituteRequest.status == SUBSTITUTE_ACCEPTED_STATUS,
            SubstituteRequest.responded_at.is_not(None),
            SubstituteRequest.responded_at >= since,
            other_user=SubstituteRequest.target_user_id,
            at=SubstituteRequest.responded_at,
        )

    async def list_rejected_substitutes(
        self,
        store_id: UUID,
        user_id: UUID,
        since: datetime,
    ) -> list[SubstituteEvent]:
        """내가 보낸 대타 요청 중 상대가 거절한 것을 조회합니다."""
        return await self._substitutes(
            store_id,
            SubstituteRequest.requester_user_id == user_id,
            SubstituteRequest.status == SUBSTITUTE_REJECTED_STATUS,
            SubstituteRequest.responded_at.is_not(None),
            SubstituteRequest.responded_at >= since,
            other_user=SubstituteRequest.target_user_id,
            at=SubstituteRequest.responded_at,
        )

    async def list_schedule_changes(
        self,
        store_id: UUID,
        user_id: UUID,
        since: datetime,
    ) -> list[ScheduleChangeEvent]:
        """사장님이 바꾼 내 하루 근무 기록을 조회합니다."""
        query = select(
            ScheduleChangeNotice.id,
            ScheduleChangeNotice.work_date,
            ScheduleChangeNotice.change,
            ScheduleChangeNotice.shifts_text,
            ScheduleChangeNotice.created_at,
        ).where(
            ScheduleChangeNotice.store_id == store_id,
            ScheduleChangeNotice.user_id == user_id,
            ScheduleChangeNotice.created_at >= since,
        )
        rows = (await self._session.execute(query)).all()
        return [ScheduleChangeEvent(*row) for row in rows]

    async def list_answered_questions(
        self,
        store_id: UUID,
        user_id: UUID,
        since: datetime,
    ) -> list[AnswerEvent]:
        """사장님이 답한 내 질문을 조회합니다."""
        query = select(
            OwnerQuestion.id,
            OwnerQuestion.chat_id,
            OwnerQuestion.question,
            OwnerQuestion.answered_at,
        ).where(
            OwnerQuestion.store_id == store_id,
            OwnerQuestion.asked_by == user_id,
            OwnerQuestion.status == OWNER_QUESTION_ANSWERED,
            OwnerQuestion.answered_at.is_not(None),
            OwnerQuestion.answered_at >= since,
        )
        rows = (await self._session.execute(query)).all()
        return [
            AnswerEvent(question_id, chat_id, question, answered_at)
            for question_id, chat_id, question, answered_at in rows
            if answered_at is not None
        ]

    async def list_handovers(
        self,
        store_id: UUID,
        exclude_user_id: UUID,
        since: datetime,
    ) -> list[HandoverEvent]:
        """다른 사람이 남긴 인수인계를 작성자 이름과 함께 조회합니다."""
        name, user, member = self._name_of()
        query = (
            select(HandoverNote.id, name, HandoverNote.summary, HandoverNote.created_at)
            .join(user, user.id == HandoverNote.author_id)
            .outerjoin(
                member,
                and_(
                    member.store_id == store_id,
                    member.user_id == HandoverNote.author_id,
                ),
            )
            .where(
                HandoverNote.store_id == store_id,
                HandoverNote.author_id != exclude_user_id,
                HandoverNote.deleted_at.is_(None),
                HandoverNote.created_at >= since,
            )
        )
        rows = (await self._session.execute(query)).all()
        return [HandoverEvent(*row) for row in rows]

    async def list_owner_questions(
        self,
        store_id: UUID,
        since: datetime,
    ) -> list[QuestionEvent]:
        """매장에 들어온 질문을 질문한 직원 이름과 함께 조회합니다."""
        name, user, member = self._name_of()
        query = (
            select(
                OwnerQuestion.id, name, OwnerQuestion.question, OwnerQuestion.created_at
            )
            .join(user, user.id == OwnerQuestion.asked_by)
            .outerjoin(
                member,
                and_(
                    member.store_id == store_id,
                    member.user_id == OwnerQuestion.asked_by,
                ),
            )
            .where(
                OwnerQuestion.store_id == store_id,
                OwnerQuestion.created_at >= since,
            )
        )
        rows = (await self._session.execute(query)).all()
        return [QuestionEvent(*row) for row in rows]

    async def list_unchecked_items(
        self,
        store_id: UUID,
        start_date: date,
        end_date: date,
    ) -> list[UncheckedItem]:
        """기간 안 인수인계 중 아직 체크되지 않은 항목을 최신 날짜 순으로 조회합니다."""
        name, user, member = self._name_of()
        query = (
            select(
                HandoverNote.id,
                HandoverItem.id,
                HandoverItem.tag,
                HandoverItem.text,
                name,
                HandoverNote.work_date,
            )
            .join(HandoverNote, HandoverNote.id == HandoverItem.note_id)
            .join(user, user.id == HandoverNote.author_id)
            .outerjoin(
                member,
                and_(
                    member.store_id == store_id,
                    member.user_id == HandoverNote.author_id,
                ),
            )
            .where(
                HandoverNote.store_id == store_id,
                HandoverNote.deleted_at.is_(None),
                HandoverNote.work_date.between(start_date, end_date),
                HandoverItem.checked.is_(False),
            )
            .order_by(
                HandoverNote.work_date.desc(),
                HandoverNote.created_at,
                HandoverItem.position,
            )
        )
        rows = (await self._session.execute(query)).all()
        return [UncheckedItem(*row) for row in rows]

    async def get_last_read_at(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> datetime | None:
        """사용자가 매장 알림 화면을 마지막으로 연 시각을 조회합니다."""
        result = await self._session.execute(
            select(NotificationRead.last_read_at).where(
                NotificationRead.store_id == store_id,
                NotificationRead.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def _get_read(self, store_id: UUID, user_id: UUID) -> NotificationRead | None:
        """읽음 기록 행을 조회합니다."""
        result = await self._session.execute(
            select(NotificationRead).where(
                NotificationRead.store_id == store_id,
                NotificationRead.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def mark_read(
        self,
        store_id: UUID,
        user_id: UUID,
        read_at: datetime,
    ) -> None:
        """알림 화면을 연 시각을 저장하고, 동시에 만들어지면 다시 갱신합니다."""
        for _ in range(2):
            record = await self._get_read(store_id, user_id)
            if record is None:
                record = NotificationRead(
                    store_id=store_id,
                    user_id=user_id,
                    last_read_at=read_at,
                )
            else:
                record.last_read_at = max(_aware(record.last_read_at), read_at)
            self._session.add(record)
            try:
                await self._session.commit()
                return
            except IntegrityError:
                await self._session.rollback()
            except SQLAlchemyError:
                await self._session.rollback()
                raise
        raise RuntimeError("notification read state could not be saved")
