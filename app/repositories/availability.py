from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.availability import Availability


class AvailabilityRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_member_and_month(
        self,
        store_id: UUID,
        membership_id: UUID,
        month: date,
    ) -> Availability | None:
        """구성원이 해당 매장과 월에 제출한 가능 시간을 조회합니다."""
        query = (
            select(Availability)
            .options(selectinload(Availability.days))
            .where(
                Availability.store_id == store_id,
                Availability.membership_id == membership_id,
                Availability.month == month,
            )
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_id_and_member(
        self,
        availability_id: UUID,
        store_id: UUID,
        membership_id: UUID,
    ) -> Availability | None:
        """구성원 본인의 제출 하나를 ID로 조회합니다."""
        query = (
            select(Availability)
            .options(selectinload(Availability.days))
            .where(
                Availability.id == availability_id,
                Availability.store_id == store_id,
                Availability.membership_id == membership_id,
            )
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list_by_store_and_month(
        self,
        store_id: UUID,
        month: date,
    ) -> list[Availability]:
        """매장의 월별 제출을 직원 가입 순서로 조회합니다."""
        query = (
            select(Availability)
            .options(selectinload(Availability.days))
            .where(
                Availability.store_id == store_id,
                Availability.month == month,
            )
            .order_by(Availability.submitted_at, Availability.id)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create(self, availability: Availability) -> bool:
        """제출을 저장하고 같은 월의 중복 제출이면 False를 반환합니다."""
        self._session.add(availability)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            return False
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(availability)
        return True

    async def save(self, availability: Availability) -> Availability:
        """수정된 제출과 날짜 목록을 저장합니다."""
        self._session.add(availability)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(availability)
        return availability

    async def delete(self, availability: Availability) -> None:
        """제출과 연결 날짜를 삭제합니다."""
        await self._session.delete(availability)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
