from datetime import datetime
from typing import Literal
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.invitation import Invitation
from app.models.membership import Membership
from app.models.store import Store
from app.models.user import User

UserStoreRecord = tuple[
    Store,
    Literal["owner", "staff"],
    str,
    UUID | None,
    str | None,
    datetime,
]


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_store_roles_for_user(
        self,
        user_id: UUID,
    ) -> list[UserStoreRecord]:
        owner_query = (
            select(Store, User.nickname)
            .join(User, User.id == Store.owner_id)
            .where(Store.owner_id == user_id, Store.deleted_at.is_(None))
            .order_by(Store.created_at, Store.id)
        )
        owner_result = await self._session.execute(owner_query)
        stores: list[UserStoreRecord] = [
            (store, "owner", owner_name, None, None, store.created_at)
            for store, owner_name in owner_result.all()
        ]

        staff_query = (
            select(
                Store,
                User.nickname,
                Membership.id,
                Membership.staff_name,
                Membership.joined_at,
            )
            .join(Membership, Membership.store_id == Store.id)
            .join(User, User.id == Store.owner_id)
            .where(
                Membership.user_id == user_id,
                Membership.left_at.is_(None),
                Store.deleted_at.is_(None),
            )
            .order_by(Membership.joined_at, Membership.id)
        )
        staff_result = await self._session.execute(staff_query)
        stores.extend(
            (
                store,
                "staff",
                owner_name,
                member_id,
                staff_name,
                joined_at,
            )
            for (
                store,
                owner_name,
                member_id,
                staff_name,
                joined_at,
            ) in staff_result.all()
        )
        return stores

    async def get_active_by_store_and_user_id(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> Membership | None:
        """삭제되지 않은 매장의 재직 중인 구성원을 조회합니다."""
        query = (
            select(Membership)
            .join(Store, Store.id == Membership.store_id)
            .where(
                Membership.store_id == store_id,
                Membership.user_id == user_id,
                Membership.left_at.is_(None),
                Store.deleted_at.is_(None),
            )
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    def _accepted_invitation_id(self):
        return (
            select(Invitation.id)
            .where(
                Invitation.store_id == Membership.store_id,
                Invitation.accepted_by_user_id == Membership.user_id,
                Invitation.accepted_at.is_not(None),
            )
            .order_by(Invitation.accepted_at.desc(), Invitation.id.desc())
            .limit(1)
            .correlate(Membership)
            .scalar_subquery()
        )

    async def list_active_by_store_id(self, store_id: UUID) -> list[Membership]:
        """삭제되지 않은 매장의 재직 중인 구성원을 가입 순서로 조회합니다."""
        query = (
            select(Membership)
            .join(Store, Store.id == Membership.store_id)
            .where(
                Membership.store_id == store_id,
                Membership.left_at.is_(None),
                Store.deleted_at.is_(None),
            )
            .order_by(Membership.joined_at, Membership.id)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def list_by_store_id(
        self,
        store_id: UUID,
    ) -> list[tuple[Membership, UUID | None]]:
        query = (
            select(
                Membership,
                self._accepted_invitation_id().label("invitation_id"),
            )
            .where(Membership.store_id == store_id)
            .order_by(Membership.joined_at.desc(), Membership.id.desc())
        )
        result = await self._session.execute(query)
        return [(row[0], row[1]) for row in result.all()]

    async def get_by_id_and_store_id(
        self,
        member_id: UUID,
        store_id: UUID,
    ) -> tuple[Membership, UUID | None] | None:
        query = select(
            Membership,
            self._accepted_invitation_id().label("invitation_id"),
        ).where(
            Membership.id == member_id,
            Membership.store_id == store_id,
        )
        result = await self._session.execute(query)
        row = result.one_or_none()
        if row is None:
            return None
        return row[0], row[1]

    async def leave(
        self,
        membership: Membership,
        left_at: datetime,
    ) -> Membership:
        membership.left_at = left_at
        self._session.add(membership)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(membership)
        return membership
