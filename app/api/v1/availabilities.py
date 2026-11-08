from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.availability import AvailabilityRepository
from app.repositories.membership import MembershipRepository
from app.repositories.store import StoreRepository
from app.schemas.availability import (
    AvailabilityCreateRequest,
    AvailabilityDayInput,
    AvailabilityInput,
    AvailabilityResponse,
    AvailabilityStatus,
    AvailabilitySubmissionItem,
    AvailabilitySubmissionListResponse,
    StoreAvailabilityItem,
    StoreAvailabilityListResponse,
)
from app.services.availability import (
    AvailabilityClosedError,
    AvailabilityExistsError,
    AvailabilityInvalidDaysError,
    AvailabilityNotFoundError,
    AvailabilityPeriod,
    AvailabilityService,
    AvailabilityStaffOnlyError,
    AvailabilityView,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import (
    StoreAccessForbiddenError,
    StoreAccessService,
)

router = APIRouter(prefix="/stores/{store_id}", tags=["availabilities"])


def get_availability_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> AvailabilityService:
    memberships = MembershipRepository(session)
    return AvailabilityService(
        AvailabilityRepository(session),
        memberships,
        StoreAccessService(StoreRepository(session), memberships),
    )


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "detail": None},
    )


@contextmanager
def _translate_access_errors() -> Iterator[None]:
    try:
        yield
    except StoreAccessForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner permission required",
        ) from None
    except StoreNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        ) from None


def _month_key(period: AvailabilityPeriod) -> str:
    return f"{period.month.year:04d}-{period.month.month:02d}"


def _to_response(view: AvailabilityView) -> AvailabilityResponse:
    item = view.availability
    return AvailabilityResponse(
        availability_id=item.id if item else None,
        month=_month_key(view.period),
        deadline=view.period.deadline,
        days=(
            [
                AvailabilityDayInput(
                    date=day.work_date,
                    status=cast(AvailabilityStatus, day.status),
                )
                for day in item.days
            ]
            if item
            else []
        ),
        memo=item.memo if item else "",
        submitted_at=item.submitted_at if item else None,
    )


def _availability_error(exc: Exception) -> JSONResponse:
    if isinstance(exc, AvailabilityExistsError):
        return _error(
            status.HTTP_409_CONFLICT,
            "AVAILABILITY_EXISTS",
            "이미 낸 근무 가능 시간이 있어요",
        )
    if isinstance(exc, AvailabilityClosedError):
        return _error(
            status.HTTP_409_CONFLICT,
            "AVAILABILITY_CLOSED",
            "근무 가능 시간 제출이 마감됐어요",
        )
    if isinstance(exc, AvailabilityNotFoundError):
        return _error(
            status.HTTP_404_NOT_FOUND,
            "NOT_FOUND",
            "근무 가능 시간을 찾지 못했어요",
        )
    if isinstance(exc, AvailabilityStaffOnlyError):
        return _error(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            "알바생만 근무 가능 시간을 제출할 수 있어요",
        )
    return _error(
        status.HTTP_422_UNPROCESSABLE_CONTENT,
        "VALIDATION_ERROR",
        "제출 날짜는 대상 월에 속해야 해요",
    )


@router.get("/availabilities/me", response_model=AvailabilityResponse)
async def get_my_availability(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AvailabilityService, Depends(get_availability_service)],
) -> AvailabilityResponse | JSONResponse:
    """현재 접수 중인 월의 내 근무 가능 시간을 조회합니다."""
    try:
        with _translate_access_errors():
            view = await service.get_mine(store_id, user.id)
    except AvailabilityStaffOnlyError as exc:
        return _availability_error(exc)
    return _to_response(view)


@router.post(
    "/availabilities",
    response_model=AvailabilityResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_availability(
    store_id: UUID,
    request: AvailabilityCreateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AvailabilityService, Depends(get_availability_service)],
) -> AvailabilityResponse | JSONResponse:
    """현재 접수 중인 월의 근무 가능 시간을 처음 제출합니다."""
    try:
        with _translate_access_errors():
            view = await service.create(
                store_id,
                user.id,
                request.month,
                request.days,
                request.memo,
            )
    except (
        AvailabilityExistsError,
        AvailabilityClosedError,
        AvailabilityStaffOnlyError,
        AvailabilityInvalidDaysError,
    ) as exc:
        return _availability_error(exc)
    return _to_response(view)


@router.patch(
    "/availabilities/{availability_id}",
    response_model=AvailabilityResponse,
)
async def update_availability(
    store_id: UUID,
    availability_id: UUID,
    request: AvailabilityInput,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AvailabilityService, Depends(get_availability_service)],
) -> AvailabilityResponse | JSONResponse:
    """제출 마감 전 내 근무 가능 시간을 다시 제출합니다."""
    try:
        with _translate_access_errors():
            view = await service.update(
                store_id,
                availability_id,
                user.id,
                request.days,
                request.memo,
            )
    except (
        AvailabilityClosedError,
        AvailabilityNotFoundError,
        AvailabilityStaffOnlyError,
        AvailabilityInvalidDaysError,
    ) as exc:
        return _availability_error(exc)
    return _to_response(view)


@router.delete(
    "/availabilities/{availability_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_model=None,
)
async def delete_availability(
    store_id: UUID,
    availability_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AvailabilityService, Depends(get_availability_service)],
) -> Response | JSONResponse:
    """내 근무 가능 시간 제출을 삭제합니다."""
    try:
        with _translate_access_errors():
            await service.delete(store_id, availability_id, user.id)
    except (AvailabilityNotFoundError, AvailabilityStaffOnlyError) as exc:
        return _availability_error(exc)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get(
    "/availabilities",
    response_model=StoreAvailabilityListResponse,
)
async def list_store_availabilities(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AvailabilityService, Depends(get_availability_service)],
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
) -> StoreAvailabilityListResponse:
    """사장님이 월별로 제출된 근무 가능 시간을 조회합니다."""
    with _translate_access_errors():
        period, views = await service.list_store_availabilities(
            store_id,
            user.id,
            month,
        )
    return StoreAvailabilityListResponse(
        month=_month_key(period),
        deadline=period.deadline,
        availabilities=[
            StoreAvailabilityItem(
                member_id=view.membership.id,
                staff_name=view.membership.staff_name,
                **_to_response(
                    AvailabilityView(view.period, view.availability)
                ).model_dump(),
            )
            for view in views
        ],
    )


@router.get(
    "/availability-submissions",
    response_model=AvailabilitySubmissionListResponse,
)
async def list_availability_submissions(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[AvailabilityService, Depends(get_availability_service)],
    month: Annotated[str | None, Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$")] = None,
) -> AvailabilitySubmissionListResponse:
    """사장님이 재직 구성원의 월별 제출 현황을 조회합니다."""
    with _translate_access_errors():
        period, views = await service.list_submissions(store_id, user.id, month)
    items = [
        AvailabilitySubmissionItem(
            member_id=view.membership.id,
            staff_name=view.membership.staff_name,
            submitted=view.availability is not None,
            submitted_at=(
                view.availability.submitted_at if view.availability else None
            ),
        )
        for view in views
    ]
    return AvailabilitySubmissionListResponse(
        month=_month_key(period),
        deadline=period.deadline,
        total_members=len(items),
        submitted_count=sum(item.submitted for item in items),
        members=items,
    )
