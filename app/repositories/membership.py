from uuid import UUID

from sqlalchemy import select
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
