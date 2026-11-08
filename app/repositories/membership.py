from datetime import datetime
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import Membership
from app.models.store import Store


class MembershipRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_store_roles_for_user(
        self,
        user_id: UUID,
    ) -> list[tuple[Store, str]]:
        owner_query = (
            select(Store)
            .where(Store.owner_id == user_id, Store.deleted_at.is_(None))
            .order_by(Store.created_at, Store.id)
        )
        owner_result = await self._session.execute(owner_query)
        stores = [(store, "owner") for store in owner_result.scalars().all()]

        staff_query = (
            select(Store)
            .join(Membership, Membership.store_id == Store.id)
            .where(
                Membership.user_id == user_id,
                Membership.left_at.is_(None),
                Store.deleted_at.is_(None),
            )
            .order_by(Membership.joined_at, Membership.id)
        )
        staff_result = await self._session.execute(staff_query)
        stores.extend((store, "staff") for store in staff_result.scalars().all())
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

    async def list_by_store_id(self, store_id: UUID) -> list[Membership]:
        query = (
            select(Membership)
            .where(Membership.store_id == store_id)
            .order_by(Membership.joined_at.desc(), Membership.id.desc())
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_by_id_and_store_id(
        self,
        member_id: UUID,
        store_id: UUID,
    ) -> Membership | None:
        query = select(Membership).where(
            Membership.id == member_id,
            Membership.store_id == store_id,
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

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
