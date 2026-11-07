from uuid import UUID

from sqlalchemy import select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import Invitation, InvitationAttempt
from app.models.membership import Membership
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
        return invitation

    async def get_context_by_code(self, code: str) -> InvitationContext | None:
        query = (
            select(Invitation, Store, User)
            .join(Store, Store.id == Invitation.store_id)
            .join(User, User.id == Store.owner_id)
            .where(Invitation.code == code)
        )
        result = await self._session.execute(query)
        row = result.one_or_none()
        if row is None:
            return None
        return row[0], row[1], row[2]

    async def get_by_id_and_store_id(
        self,
        invitation_id: UUID,
        store_id: UUID,
    ) -> Invitation | None:
        query = select(Invitation).where(
            Invitation.id == invitation_id,
            Invitation.store_id == store_id,
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

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
        return invitation

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
