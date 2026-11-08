from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date, timedelta
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user
from app.db.session import get_db
from app.models.schedule import Schedule, ScheduleRecommendation
from app.models.user import User
from app.repositories.membership import MembershipRepository
from app.repositories.schedule import ScheduleRepository
from app.repositories.store import StoreRepository
from app.schemas.schedule import (
    MyScheduleResponse,
    MyScheduleShiftResponse,
    RecommendationCreateRequest,
    RecommendationCreateResponse,
    RecommendationDetailResponse,
    RecommendationListResponse,
    RecommendationRules,
    RecommendationShiftResponse,
    RecommendationSummaryResponse,
    ScheduleAssignmentResponse,
    ScheduleCreateRequest,
    ScheduleListResponse,
    ScheduleResponse,
    ScheduleShiftResponse,
    ScheduleUpdateRequest,
)
from app.services.schedule import (
    RecommendationNotFoundError,
    ScheduleAlreadyConfirmedError,
    ScheduleAssignmentConflictError,
    ScheduleInvalidMemberError,
    ScheduleNotFoundError,
    ScheduleService,
    ScheduleStaffOnlyError,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError, StoreAccessService

router = APIRouter(prefix="/stores/{store_id}", tags=["schedules"])


def get_schedule_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ScheduleService:
    memberships = MembershipRepository(session)
    return ScheduleService(
        ScheduleRepository(session),
        memberships,
        StoreAccessService(StoreRepository(session), memberships),
    )


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "detail": None},
    )


@contextmanager
def _translate_errors() -> Iterator[None]:
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
    except RecommendationNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule recommendation not found",
        ) from None
    except ScheduleNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Schedule not found",
        ) from None


def _time_text(value) -> str:
    return value.strftime("%H:%M")


def _recommendation_summary(
    item: ScheduleRecommendation,
) -> RecommendationSummaryResponse:
    return RecommendationSummaryResponse(
        recommendation_id=item.id,
        batch_id=item.batch_id,
        candidate_no=item.candidate_no,
        start_date=item.start_date,
        end_date=item.end_date,
        unfilled_slots=item.unfilled_slots,
        created_at=item.created_at,
    )


def _recommendation_detail(
    item: ScheduleRecommendation,
    names: dict[UUID, str],
) -> RecommendationDetailResponse:
    warnings: list[str] = []
    shifts: list[RecommendationShiftResponse] = []
    for shift in item.shifts:
        shortage = shift.required_staff - len(shift.assignments)
        if shortage > 0:
            warnings.append(
                f"{shift.work_date.isoformat()} {_time_text(shift.start_time)}-"
                f"{_time_text(shift.end_time)} 근무가 {shortage}명 부족해요"
            )
        shifts.append(
            RecommendationShiftResponse(
                shift_id=shift.id,
                date=shift.work_date,
                start=_time_text(shift.start_time),
                end=_time_text(shift.end_time),
                role=shift.role,
                required_staff=shift.required_staff,
                assignments=[
                    ScheduleAssignmentResponse(
                        member_id=assignment.membership_id,
                        staff_name=names.get(assignment.membership_id, "퇴사한 직원"),
                    )
                    for assignment in shift.assignments
                ],
            )
        )
    return RecommendationDetailResponse(
        **_recommendation_summary(item).model_dump(),
        rules=RecommendationRules(
            maximum_weekly_hours=item.maximum_weekly_hours,
            minimum_rest_minutes=item.minimum_rest_minutes,
        ),
        shifts=shifts,
        warnings=warnings,
    )


def _schedule_response(
    item: Schedule,
    names: dict[UUID, str],
) -> ScheduleResponse:
    return ScheduleResponse(
        schedule_id=item.id,
        recommendation_id=item.recommendation_id,
        name=item.name,
        start_date=item.start_date,
        end_date=item.end_date,
        status=cast(Literal["draft", "published"], item.status),
        published_at=item.published_at,
        shifts=[
            ScheduleShiftResponse(
                shift_id=shift.id,
                date=shift.work_date,
                start=_time_text(shift.start_time),
                end=_time_text(shift.end_time),
                role=shift.role,
                assignments=[
                    ScheduleAssignmentResponse(
                        member_id=assignment.membership_id,
                        staff_name=names.get(assignment.membership_id, "퇴사한 직원"),
                    )
                    for assignment in shift.assignments
                ],
            )
            for shift in item.shifts
        ],
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


@router.post(
    "/schedule-recommendations",
    response_model=RecommendationCreateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_schedule_recommendations(
    store_id: UUID,
    request: RecommendationCreateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> RecommendationCreateResponse:
    """제출된 가능 시간을 바탕으로 서로 다른 추천 후보를 생성합니다."""
    with _translate_errors():
        recommendations = await service.create_recommendations(
            store_id, user.id, request
        )
    names = await service.member_names(store_id)
    return RecommendationCreateResponse(
        batch_id=recommendations[0].batch_id,
        recommendations=[
            _recommendation_detail(item, names) for item in recommendations
        ],
    )


@router.get(
    "/schedule-recommendations",
    response_model=RecommendationListResponse,
)
async def list_schedule_recommendations(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> RecommendationListResponse:
    """생성된 추천 후보 목록을 최신 순서로 조회합니다."""
    with _translate_errors():
        items = await service.list_recommendations(store_id, user.id)
    return RecommendationListResponse(
        recommendations=[_recommendation_summary(item) for item in items]
    )


@router.get(
    "/schedule-recommendations/{recommendation_id}",
    response_model=RecommendationDetailResponse,
)
async def get_schedule_recommendation(
    store_id: UUID,
    recommendation_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> RecommendationDetailResponse:
    """추천 후보의 근무 칸과 직원 배정을 조회합니다."""
    with _translate_errors():
        item = await service.get_recommendation(
            store_id, recommendation_id, user.id
        )
    names = await service.member_names(store_id)
    return _recommendation_detail(item, names)


@router.post(
    "/schedules",
    response_model=ScheduleResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_schedule(
    store_id: UUID,
    request: ScheduleCreateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> ScheduleResponse | JSONResponse:
    """추천 후보 하나를 실제 스케줄로 등록합니다."""
    try:
        with _translate_errors():
            item = await service.create_schedule(
                store_id,
                request.recommendation_id,
                user.id,
                request.name,
                publish=request.publish,
            )
    except ScheduleAlreadyConfirmedError:
        return _error(
            status.HTTP_409_CONFLICT,
            "SCHEDULE_ALREADY_CONFIRMED",
            "이미 스케줄로 등록한 추천 후보예요",
        )
    names = await service.member_names(store_id)
    return _schedule_response(item, names)


@router.get("/schedules", response_model=ScheduleListResponse)
async def list_schedules(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
    start_date: Annotated[date | None, Query(alias="startDate")] = None,
    end_date: Annotated[date | None, Query(alias="endDate")] = None,
) -> ScheduleListResponse:
    """사장님이 등록한 스케줄을 기간으로 조회합니다."""
    with _translate_errors():
        items = await service.list_schedules(
            store_id, user.id, start_date, end_date
        )
    names = await service.member_names(store_id)
    return ScheduleListResponse(
        schedules=[_schedule_response(item, names) for item in items]
    )


@router.patch("/schedules/{schedule_id}", response_model=ScheduleResponse)
async def update_schedule(
    store_id: UUID,
    schedule_id: UUID,
    request: ScheduleUpdateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> ScheduleResponse | JSONResponse:
    """스케줄의 근무 배정을 조정하거나 공개 상태를 변경합니다."""
    try:
        with _translate_errors():
            item = await service.update_schedule(
                store_id, schedule_id, user.id, request
            )
    except ScheduleInvalidMemberError:
        return _error(
            status.HTTP_422_UNPROCESSABLE_CONTENT,
            "INVALID_MEMBER",
            "배정할 수 없는 구성원이 포함되어 있어요",
        )
    except ScheduleAssignmentConflictError:
        return _error(
            status.HTTP_409_CONFLICT,
            "ASSIGNMENT_CONFLICT",
            "같은 직원의 근무 시간이 겹쳐요",
        )
    names = await service.member_names(store_id)
    return _schedule_response(item, names)


@router.get("/schedules/me", response_model=MyScheduleResponse)
async def get_my_schedule(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> MyScheduleResponse | JSONResponse:
    """알바생이 공개된 본인 근무표를 조회합니다."""
    try:
        with _translate_errors():
            today, week_start, member, schedules, names = await service.my_schedule(
                store_id, user.id
            )
    except ScheduleStaffOnlyError:
        return _error(
            status.HTTP_403_FORBIDDEN,
            "FORBIDDEN",
            "알바생만 내 근무표를 조회할 수 있어요",
        )

    shifts: list[MyScheduleShiftResponse] = []
    week_minutes = 0
    week_end = week_start + timedelta(days=6)
    for schedule in schedules:
        for shift in schedule.shifts:
            assigned_ids = {item.membership_id for item in shift.assignments}
            if member.id not in assigned_ids:
                continue
            if week_start <= shift.work_date <= week_end:
                start_minutes = shift.start_time.hour * 60 + shift.start_time.minute
                end_minutes = shift.end_time.hour * 60 + shift.end_time.minute
                week_minutes += end_minutes - start_minutes
            shifts.append(
                MyScheduleShiftResponse(
                    shift_id=shift.id,
                    date=shift.work_date,
                    start=_time_text(shift.start_time),
                    end=_time_text(shift.end_time),
                    role=shift.role,
                    crew=[
                        names.get(item.membership_id, "퇴사한 직원")
                        for item in shift.assignments
                        if item.membership_id != member.id
                    ],
                )
            )
    shifts.sort(key=lambda item: (item.date, item.start))
    week_hours = week_minutes / 60
    if week_hours >= 15:
        note = f"이번 주 {week_hours:g}시간 · 주휴수당 대상"
    else:
        note = f"이번 주 {week_hours:g}시간 · {15 - week_hours:g}시간 더 필요"
    return MyScheduleResponse(
        today=today,
        week_start=week_start,
        week_hours=week_hours,
        week_note=note,
        shifts=shifts,
    )
