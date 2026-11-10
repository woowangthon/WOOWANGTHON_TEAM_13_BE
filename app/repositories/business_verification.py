from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.business_verification import BusinessVerification


class BusinessVerificationRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def create(
        self,
        verification: BusinessVerification,
    ) -> BusinessVerification:
        self._session.add(verification)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(verification)
        return verification

    async def get_by_id_and_requester_id(
        self,
        verification_id: int,
        requester_id: UUID,
    ) -> BusinessVerification | None:
        query = select(BusinessVerification).where(
            BusinessVerification.id == verification_id,
            BusinessVerification.requester_id == requester_id,
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()
