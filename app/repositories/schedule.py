from datetime import date, datetime
from uuid import UUID

from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.membership import Membership
from app.models.schedule import (
    ScheduleAssignment,
    ScheduleAssignmentOverride,
    ShiftTemplate,
    SubstituteRequest,
)
from app.models.store import Store
from app.models.user import User

WorkerRecord = tuple[UUID, UUID | None, str, str]


class PendingSubstituteRequestExistsError(Exception):
    pass


class ScheduleRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_workers(self, store_id: UUID) -> list[WorkerRecord]:
        owner_query = (
            select(Store.owner_id, User.nickname)
            .join(User, User.id == Store.owner_id)
            .where(Store.id == store_id, Store.deleted_at.is_(None))
        )
        owner = (await self._session.execute(owner_query)).one_or_none()
        if owner is None:
            return []
        result: list[WorkerRecord] = [(owner[0], None, owner[1], "owner")]
        staff_query = (
            select(
                Membership.user_id,
                Membership.id,
                Membership.staff_name,
            )
            .where(
                Membership.store_id == store_id,
                Membership.left_at.is_(None),
            )
            .order_by(Membership.joined_at, Membership.id)
        )
        staff = await self._session.execute(staff_query)
        result.extend((row[0], row[1], row[2], "staff") for row in staff.all())
        return result

    async def get_store_closure(self, store_id: UUID) -> tuple[list[int], bool]:
        query = select(Store.closed_weekdays, Store.closed_on_holidays).where(
            Store.id == store_id,
            Store.deleted_at.is_(None),
        )
        row = (await self._session.execute(query)).one()
        return list(row[0]), row[1]

    async def create_template(self, template: ShiftTemplate) -> ShiftTemplate:
        self._session.add(template)
        await self._commit()
        await self._session.refresh(template)
        return template

    async def list_templates(self, store_id: UUID) -> list[ShiftTemplate]:
        query = (
            select(ShiftTemplate)
            .where(ShiftTemplate.store_id == store_id)
            .order_by(
                ShiftTemplate.sort_order, ShiftTemplate.start_time, ShiftTemplate.id
            )
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_template(
        self, store_id: UUID, template_id: UUID
    ) -> ShiftTemplate | None:
        query = select(ShiftTemplate).where(
            ShiftTemplate.id == template_id,
            ShiftTemplate.store_id == store_id,
        )
        return (await self._session.execute(query)).scalar_one_or_none()

    async def save_template(self, template: ShiftTemplate) -> ShiftTemplate:
        self._session.add(template)
        await self._commit()
        await self._session.refresh(template)
        return template

    async def delete_template(self, template: ShiftTemplate) -> None:
        await self._session.delete(template)
        await self._commit()

    async def replace_assignments(
        self,
        store_id: UUID,
        assignments: list[ScheduleAssignment],
    ) -> list[ScheduleAssignment]:
        await self._session.execute(
            delete(ScheduleAssignment).where(
                ScheduleAssignment.store_id == store_id
            )
        )
        self._session.add_all(assignments)
        await self._commit()
        return await self.list_assignments(store_id)

    async def list_assignments(self, store_id: UUID) -> list[ScheduleAssignment]:
        query = (
            select(ScheduleAssignment)
            .options(selectinload(ScheduleAssignment.template))
            .where(ScheduleAssignment.store_id == store_id)
            .order_by(
                ScheduleAssignment.weekday,
                ScheduleAssignment.template_id,
                ScheduleAssignment.id,
            )
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_assignment(
        self, store_id: UUID, assignment_id: UUID
    ) -> ScheduleAssignment | None:
        query = (
            select(ScheduleAssignment)
            .options(selectinload(ScheduleAssignment.template))
            .where(
                ScheduleAssignment.id == assignment_id,
                ScheduleAssignment.store_id == store_id,
            )
        )
        return (await self._session.execute(query)).scalar_one_or_none()

    async def list_overrides(
        self,
        assignment_ids: list[UUID],
        start_date: date,
        end_date: date,
    ) -> list[ScheduleAssignmentOverride]:
        if not assignment_ids:
            return []
        query = select(ScheduleAssignmentOverride).where(
            ScheduleAssignmentOverride.schedule_assignment_id.in_(assignment_ids),
            ScheduleAssignmentOverride.work_date.between(start_date, end_date),
        )
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def get_override(
        self, assignment_id: UUID, work_date: date
    ) -> ScheduleAssignmentOverride | None:
        query = select(ScheduleAssignmentOverride).where(
            ScheduleAssignmentOverride.schedule_assignment_id == assignment_id,
            ScheduleAssignmentOverride.work_date == work_date,
        )
        return (await self._session.execute(query)).scalar_one_or_none()

    async def find_pending_request(
        self, assignment_id: UUID, work_date: date
    ) -> SubstituteRequest | None:
        query = select(SubstituteRequest).where(
            SubstituteRequest.schedule_assignment_id == assignment_id,
            SubstituteRequest.work_date == work_date,
            SubstituteRequest.status == "PENDING",
        )
        return (await self._session.execute(query)).scalar_one_or_none()

    async def create_request(self, request: SubstituteRequest) -> SubstituteRequest:
        self._session.add(request)
        try:
            await self._session.commit()
        except IntegrityError as exc:
            await self._session.rollback()
            raise PendingSubstituteRequestExistsError from exc
        await self._session.refresh(request)
        return await self.get_request(request.store_id, request.id) or request

    async def get_request(
        self,
        store_id: UUID,
        request_id: UUID,
        *,
        for_update: bool = False,
    ) -> SubstituteRequest | None:
        query = (
            select(SubstituteRequest)
            .options(
                selectinload(SubstituteRequest.assignment).selectinload(
                    ScheduleAssignment.template
                )
            )
            .where(
                SubstituteRequest.id == request_id,
                SubstituteRequest.store_id == store_id,
            )
        )
        if for_update:
            query = query.with_for_update()
        return (await self._session.execute(query)).scalar_one_or_none()

    async def list_requests(
        self,
        store_id: UUID,
        user_id: UUID,
        box: str,
        status: str | None,
    ) -> list[SubstituteRequest]:
        user_filter = (
            SubstituteRequest.target_user_id == user_id
            if box == "received"
            else SubstituteRequest.requester_user_id == user_id
        )
        query = (
            select(SubstituteRequest)
            .options(
                selectinload(SubstituteRequest.assignment).selectinload(
                    ScheduleAssignment.template
                )
            )
            .where(SubstituteRequest.store_id == store_id, user_filter)
            .order_by(SubstituteRequest.created_at.desc(), SubstituteRequest.id.desc())
        )
        if status is not None:
            query = query.where(SubstituteRequest.status == status)
        result = await self._session.execute(query)
        return list(result.scalars().all())

    async def respond(
        self,
        request: SubstituteRequest,
        responded_at: datetime,
        *,
        accept: bool,
    ) -> SubstituteRequest:
        request.status = "ACCEPTED" if accept else "REJECTED"
        request.responded_at = responded_at
        request.target_read_at = request.target_read_at or responded_at
        if accept:
            existing = await self.get_override(
                request.schedule_assignment_id,
                request.work_date,
            )
            if existing is None:
                self._session.add(
                    ScheduleAssignmentOverride(
                        schedule_assignment_id=request.schedule_assignment_id,
                        work_date=request.work_date,
                        assignee_user_id=request.target_user_id,
                        substitute_request_id=request.id,
                    )
                )
            else:
                existing.assignee_user_id = request.target_user_id
                existing.substitute_request_id = request.id
                self._session.add(existing)
        self._session.add(request)
        await self._commit()
        return await self.get_request(request.store_id, request.id) or request

    async def mark_received_read(
        self, requests: list[SubstituteRequest], read_at: datetime
    ) -> None:
        changed = False
        for request in requests:
            if request.target_read_at is None:
                request.target_read_at = read_at
                self._session.add(request)
                changed = True
        if changed:
            await self._commit()

    async def _commit(self) -> None:
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
