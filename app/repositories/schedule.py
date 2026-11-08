from datetime import date
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.availability import Availability
from app.models.schedule import (
    RecommendationShift,
    Schedule,
    ScheduleRecommendation,
    ScheduleShift,
)


class ScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    @staticmethod
    def _recommendation_options():
        return selectinload(ScheduleRecommendation.shifts).selectinload(
            RecommendationShift.assignments
        )

    @staticmethod
    def _schedule_options():
        return selectinload(Schedule.shifts).selectinload(
            ScheduleShift.assignments
        )

    async def list_availabilities(
        self,
        store_id: UUID,
        months: list[date],
    ) -> list[Availability]:
        query = (
            select(Availability)
            .options(selectinload(Availability.days))
            .where(
                Availability.store_id == store_id,
                Availability.month.in_(months),
            )
            .order_by(Availability.submitted_at, Availability.id)
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def create_recommendations(
        self,
        recommendations: list[ScheduleRecommendation],
    ) -> list[ScheduleRecommendation]:
        self._session.add_all(recommendations)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        return recommendations

    async def list_recommendations(
        self,
        store_id: UUID,
    ) -> list[ScheduleRecommendation]:
        query = (
            select(ScheduleRecommendation)
            .where(ScheduleRecommendation.store_id == store_id)
            .order_by(
                ScheduleRecommendation.created_at.desc(),
                ScheduleRecommendation.batch_id.desc(),
                ScheduleRecommendation.candidate_no,
            )
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_recommendation(
        self,
        store_id: UUID,
        recommendation_id: UUID,
    ) -> ScheduleRecommendation | None:
        query = (
            select(ScheduleRecommendation)
            .options(self._recommendation_options())
            .where(
                ScheduleRecommendation.id == recommendation_id,
                ScheduleRecommendation.store_id == store_id,
            )
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def get_by_recommendation(
        self,
        recommendation_id: UUID,
    ) -> Schedule | None:
        query = select(Schedule).where(
            Schedule.recommendation_id == recommendation_id
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def create_schedule(self, schedule: Schedule) -> bool:
        self._session.add(schedule)
        try:
            await self._session.commit()
        except IntegrityError:
            await self._session.rollback()
            return False
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        return True

    async def get_schedule(
        self,
        store_id: UUID,
        schedule_id: UUID,
    ) -> Schedule | None:
        query = (
            select(Schedule)
            .options(self._schedule_options())
            .where(Schedule.id == schedule_id, Schedule.store_id == store_id)
        )
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def list_schedules(
        self,
        store_id: UUID,
        start_date: date | None = None,
        end_date: date | None = None,
        *,
        published_only: bool = False,
    ) -> list[Schedule]:
        query = select(Schedule).options(self._schedule_options()).where(
            Schedule.store_id == store_id
        )
        if published_only:
            query = query.where(Schedule.status == "published")
        if start_date is not None:
            query = query.where(Schedule.end_date >= start_date)
        if end_date is not None:
            query = query.where(Schedule.start_date <= end_date)
        query = query.order_by(Schedule.start_date.desc(), Schedule.created_at.desc())
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def save_schedule(self, schedule: Schedule) -> Schedule:
        self._session.add(schedule)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        return schedule
