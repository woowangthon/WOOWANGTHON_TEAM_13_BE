from collections.abc import Sequence
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.push_subscription import PushSubscription
from app.models.store import Store


class PushSubscriptionRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def upsert(
        self,
        user_id: UUID,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> PushSubscription:
        """endpoint 기준으로 구독을 만들거나 현재 사용자에게 다시 연결합니다."""
        result = await self._session.execute(
            select(PushSubscription).where(PushSubscription.endpoint == endpoint)
        )
        subscription = result.scalar_one_or_none()
        if subscription is None:
            subscription = PushSubscription(
                user_id=user_id,
                endpoint=endpoint,
                p256dh=p256dh,
                auth=auth,
            )
        else:
            subscription.user_id = user_id
            subscription.p256dh = p256dh
            subscription.auth = auth
        self._session.add(subscription)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(subscription)
        return subscription

    async def delete_for_user(self, user_id: UUID, endpoint: str) -> None:
        await self._session.execute(
            delete(PushSubscription).where(
                PushSubscription.user_id == user_id,
                PushSubscription.endpoint == endpoint,
            )
        )
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise

    async def list_by_user_id(self, user_id: UUID) -> list[PushSubscription]:
        result = await self._session.execute(
            select(PushSubscription).where(PushSubscription.user_id == user_id)
        )
        return list(result.scalars().all())

    async def get_store_owner_id(self, store_id: UUID) -> UUID | None:
        result = await self._session.execute(
            select(Store.owner_id).where(
                Store.id == store_id,
                Store.deleted_at.is_(None),
            )
        )
        return result.scalar_one_or_none()

    async def delete_by_ids(self, subscription_ids: Sequence[UUID]) -> None:
        if not subscription_ids:
            return
        await self._session.execute(
            delete(PushSubscription).where(PushSubscription.id.in_(subscription_ids))
        )
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
