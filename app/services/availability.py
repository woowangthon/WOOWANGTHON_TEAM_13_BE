from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime
from typing import Protocol
from uuid import UUID
from zoneinfo import ZoneInfo

from app.models.availability import Availability, AvailabilityDay
from app.models.membership import Membership
from app.schemas.availability import AvailabilityDayInput, parse_month
from app.services.store_access import StoreAccessProtocol

SEOUL = ZoneInfo("Asia/Seoul")
DEADLINE_DAY = 25


class AvailabilityExistsError(Exception):
    """같은 구성원이 같은 월의 가능 시간을 이미 제출했습니다."""


class AvailabilityClosedError(Exception):
    """제출 마감일이 지났거나 현재 접수 중인 월이 아닙니다."""


class AvailabilityNotFoundError(Exception):
    """구성원 본인의 제출을 찾을 수 없습니다."""


class AvailabilityStaffOnlyError(Exception):
    """매장 소유자가 알바생용 제출 API를 요청했습니다."""


class AvailabilityInvalidDaysError(Exception):
    """제출 날짜가 대상 월에 속하지 않습니다."""


@dataclass(frozen=True, slots=True)
class AvailabilityPeriod:
    month: date
    deadline: date


@dataclass(frozen=True, slots=True)
class AvailabilityView:
    period: AvailabilityPeriod
    availability: Availability | None


@dataclass(frozen=True, slots=True)
class StoreAvailabilityView:
    membership: Membership
    availability: Availability
    period: AvailabilityPeriod


@dataclass(frozen=True, slots=True)
class AvailabilitySubmissionView:
    membership: Membership
    availability: Availability | None


class AvailabilityRepositoryProtocol(Protocol):
    async def get_by_member_and_month(
        self,
        store_id: UUID,
        membership_id: UUID,
        month: date,
    ) -> Availability | None: ...

    async def get_by_id_and_member(
        self,
        availability_id: UUID,
        store_id: UUID,
        membership_id: UUID,
    ) -> Availability | None: ...

    async def list_by_store_and_month(
        self,
        store_id: UUID,
        month: date,
    ) -> list[Availability]: ...

    async def create(self, availability: Availability) -> bool: ...

    async def save(self, availability: Availability) -> Availability: ...

    async def delete(self, availability: Availability) -> None: ...


class MembershipRepositoryProtocol(Protocol):
    async def get_active_by_store_and_user_id(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> Membership | None: ...

    async def list_active_by_store_id(self, store_id: UUID) -> list[Membership]: ...


def _add_months(month: date, count: int) -> date:
    index = month.year * 12 + month.month - 1 + count
    year, zero_based_month = divmod(index, 12)
    return date(year, zero_based_month + 1, 1)


def deadline_for_month(month: date) -> date:
    """대상 월 직전 달의 25일을 제출 마감일로 계산합니다."""
    previous = _add_months(month, -1)
    return date(previous.year, previous.month, DEADLINE_DAY)


def active_period(today: date) -> AvailabilityPeriod:
    """현재 접수 중인 가장 가까운 근무 가능 시간 월을 반환합니다."""
    this_month = date(today.year, today.month, 1)
    this_deadline = date(today.year, today.month, DEADLINE_DAY)
    offset = 1 if today <= this_deadline else 2
    month = _add_months(this_month, offset)
    return AvailabilityPeriod(month=month, deadline=deadline_for_month(month))


def period_for_month(month: date) -> AvailabilityPeriod:
    return AvailabilityPeriod(month=month, deadline=deadline_for_month(month))


class AvailabilityService:
    def __init__(
        self,
        repository: AvailabilityRepositoryProtocol,
        memberships: MembershipRepositoryProtocol,
        store_access: StoreAccessProtocol,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        self._repository = repository
        self._memberships = memberships
        self._store_access = store_access
        self._clock = clock or (lambda: datetime.now(UTC))

    def _now(self) -> datetime:
        return self._clock()

    def _today(self) -> date:
        return self._now().astimezone(SEOUL).date()

    async def _active_membership(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> Membership:
        await self._store_access.ensure_member(store_id, user_id)
        membership = await self._memberships.get_active_by_store_and_user_id(
            store_id,
            user_id,
        )
        if membership is None:
            raise AvailabilityStaffOnlyError
        return membership

    @staticmethod
    def _validate_days(month: date, days: list[AvailabilityDayInput]) -> None:
        if any(
            (item.date.year, item.date.month) != (month.year, month.month)
            for item in days
        ):
            raise AvailabilityInvalidDaysError

    @staticmethod
    def _day_models(days: list[AvailabilityDayInput]) -> list[AvailabilityDay]:
        return [
            AvailabilityDay(work_date=item.date, status=item.status)
            for item in sorted(days, key=lambda item: item.date)
        ]

    async def get_mine(self, store_id: UUID, user_id: UUID) -> AvailabilityView:
        membership = await self._active_membership(store_id, user_id)
        period = active_period(self._today())
        availability = await self._repository.get_by_member_and_month(
            store_id,
            membership.id,
            period.month,
        )
        return AvailabilityView(period, availability)

    async def create(
        self,
        store_id: UUID,
        user_id: UUID,
        month_key: str,
        days: list[AvailabilityDayInput],
        memo: str,
    ) -> AvailabilityView:
        membership = await self._active_membership(store_id, user_id)
        month = parse_month(month_key)
        period = period_for_month(month)
        if period != active_period(self._today()) or self._today() > period.deadline:
            raise AvailabilityClosedError
        self._validate_days(month, days)

        if await self._repository.get_by_member_and_month(
            store_id,
            membership.id,
            month,
        ):
            raise AvailabilityExistsError
        availability = Availability(
            store_id=store_id,
            membership_id=membership.id,
            month=month,
            memo=memo,
            submitted_at=self._now(),
            days=self._day_models(days),
        )
        if not await self._repository.create(availability):
            raise AvailabilityExistsError
        return AvailabilityView(period, availability)

    async def update(
        self,
        store_id: UUID,
        availability_id: UUID,
        user_id: UUID,
        days: list[AvailabilityDayInput],
        memo: str,
    ) -> AvailabilityView:
        membership = await self._active_membership(store_id, user_id)
        availability = await self._repository.get_by_id_and_member(
            availability_id,
            store_id,
            membership.id,
        )
        if availability is None:
            raise AvailabilityNotFoundError
        period = period_for_month(availability.month)
        if self._today() > period.deadline:
            raise AvailabilityClosedError
        self._validate_days(availability.month, days)
        availability.days = self._day_models(days)
        availability.memo = memo
        availability.submitted_at = self._now()
        await self._repository.save(availability)
        return AvailabilityView(period, availability)

    async def delete(
        self,
        store_id: UUID,
        availability_id: UUID,
        user_id: UUID,
    ) -> None:
        membership = await self._active_membership(store_id, user_id)
        availability = await self._repository.get_by_id_and_member(
            availability_id,
            store_id,
            membership.id,
        )
        if availability is None:
            raise AvailabilityNotFoundError
        await self._repository.delete(availability)

    async def list_store_availabilities(
        self,
        store_id: UUID,
        owner_id: UUID,
        month_key: str | None,
    ) -> tuple[AvailabilityPeriod, list[StoreAvailabilityView]]:
        await self._store_access.ensure_owner(store_id, owner_id)
        period = self._resolve_period(month_key)
        memberships = await self._memberships.list_active_by_store_id(store_id)
        by_id = {membership.id: membership for membership in memberships}
        availabilities = await self._repository.list_by_store_and_month(
            store_id,
            period.month,
        )
        views = [
            StoreAvailabilityView(by_id[item.membership_id], item, period)
            for item in availabilities
            if item.membership_id in by_id
        ]
        return period, views

    async def list_submissions(
        self,
        store_id: UUID,
        owner_id: UUID,
        month_key: str | None,
    ) -> tuple[AvailabilityPeriod, list[AvailabilitySubmissionView]]:
        await self._store_access.ensure_owner(store_id, owner_id)
        period = self._resolve_period(month_key)
        memberships = await self._memberships.list_active_by_store_id(store_id)
        availabilities = await self._repository.list_by_store_and_month(
            store_id,
            period.month,
        )
        by_member = {item.membership_id: item for item in availabilities}
        return period, [
            AvailabilitySubmissionView(item, by_member.get(item.id))
            for item in memberships
        ]

    def _resolve_period(self, month_key: str | None) -> AvailabilityPeriod:
        if month_key is None:
            return active_period(self._today())
        return period_for_month(parse_month(month_key))
