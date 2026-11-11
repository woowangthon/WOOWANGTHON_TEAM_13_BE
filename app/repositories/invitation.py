from uuid import UUID

from sqlalchemy import delete, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.invitation import Invitation, InvitationAttempt
from app.models.membership import Membership
from app.models.schedule import ScheduleAssignment, ShiftTemplate
from app.models.store import Store
from app.models.user import User

InvitationContext = tuple[Invitation, Store, User]


class InvitationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(self, invitation: Invitation) -> Invitation:
        self._session.add(invitation)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(invitation)
        return (
            await self.get_by_id_and_store_id(invitation.id, invitation.store_id)
            or invitation
        )

    async def get_context_by_code(self, code: str) -> InvitationContext | None:
        query = (
            select(Invitation, Store, User)
            .options(selectinload(Invitation.schedule))
            .join(Store, Store.id == Invitation.store_id)
            .join(User, User.id == Store.owner_id)
            .where(Invitation.code == code)
        )
        result = await self._session.execute(query)
        row = result.one_or_none()
        if row is None:
            return None
        return row[0], row[1], row[2]

    async def list_by_store_id(self, store_id: UUID) -> list[Invitation]:
        query = (
            select(Invitation)
            .options(selectinload(Invitation.schedule))
            .where(Invitation.store_id == store_id)
            .order_by(Invitation.created_at.desc(), Invitation.id.desc())
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_available_by_store_and_staff_name(
        self,
        store_id: UUID,
        staff_name: str,
    ) -> Invitation | None:
        query = select(Invitation).where(
            Invitation.store_id == store_id,
            Invitation.staff_name == staff_name,
            Invitation.revoked_at.is_(None),
            Invitation.accepted_at.is_(None),
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id_and_store_id(
        self,
        invitation_id: UUID,
        store_id: UUID,
    ) -> Invitation | None:
        query = (
            select(Invitation)
            .options(selectinload(Invitation.schedule))
            .where(
                Invitation.id == invitation_id,
                Invitation.store_id == store_id,
            )
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list_shift_template_ids(self, store_id: UUID) -> set[UUID]:
        query = select(ShiftTemplate.id).where(ShiftTemplate.store_id == store_id)
        result = await self._session.execute(query)
        return set(result.scalars().all())

    async def get_active_membership(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> Membership | None:
        query = select(Membership).where(
            Membership.store_id == store_id,
            Membership.user_id == user_id,
            Membership.left_at.is_(None),
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_membership(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> Membership | None:
        query = select(Membership).where(
            Membership.store_id == store_id,
            Membership.user_id == user_id,
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def accept(
        self,
        invitation: Invitation,
        membership: Membership,
    ) -> Membership | None:
        consume_query = (
            update(Invitation)
            .where(
                Invitation.id == invitation.id,
                Invitation.revoked_at.is_(None),
                Invitation.accepted_at.is_(None),
            )
            .values(
                accepted_at=membership.joined_at,
                accepted_by_user_id=membership.user_id,
            )
            .returning(Invitation.id)
            .execution_options(synchronize_session=False)
        )
        consume_result = await self._session.execute(consume_query)
        if consume_result.scalar_one_or_none() is None:
            await self._session.rollback()
            return None

        await self._session.execute(
            delete(ScheduleAssignment).where(
                ScheduleAssignment.store_id == invitation.store_id,
                ScheduleAssignment.assignee_user_id == membership.user_id,
            )
        )
        self._session.add_all(
            [
                ScheduleAssignment(
                    store_id=invitation.store_id,
                    template_id=item.template_id,
                    weekday=item.weekday,
                    assignee_user_id=membership.user_id,
                )
                for item in invitation.schedule
            ]
        )

        self._session.add(membership)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(membership)
        return membership

    async def save(self, invitation: Invitation) -> Invitation:
        self._session.add(invitation)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(invitation)
        return (
            await self.get_by_id_and_store_id(invitation.id, invitation.store_id)
            or invitation
        )

    async def get_attempt(self, user_id: UUID) -> InvitationAttempt | None:
        return await self._session.get(InvitationAttempt, user_id)

    async def save_attempt(
        self,
        attempt: InvitationAttempt,
    ) -> InvitationAttempt:
        self._session.add(attempt)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(attempt)
        return attempt

    async def reset_attempt(self, user_id: UUID) -> None:
        attempt = await self._session.get(InvitationAttempt, user_id)
        if attempt is None:
            return
        await self._session.delete(attempt)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
