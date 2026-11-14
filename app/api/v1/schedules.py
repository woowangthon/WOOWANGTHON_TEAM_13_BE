from collections.abc import Iterator
from contextlib import contextmanager
from datetime import date
from typing import Annotated, Literal, cast
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user
from app.db.session import get_db
from app.models.schedule import (
    ScheduleAssignment,
    ShiftTemplate,
    SubstituteRequest,
)
from app.models.user import User
from app.repositories.membership import MembershipRepository
from app.repositories.schedule import ScheduleRepository
from app.repositories.schedule_change import ScheduleChangeRepository
from app.repositories.store import StoreRepository
from app.schemas.schedule import (
    CalendarShiftResponse,
    DailyScheduleReplaceRequest,
    DailyScheduleResponse,
    ScheduleAssignmentResponse,
    ScheduleCalendarResponse,
    ScheduleReplaceRequest,
    ScheduleResponse,
    ScheduleWorkerListResponse,
    ScheduleWorkerResponse,
    ShiftTemplateCreateRequest,
    ShiftTemplateListResponse,
    ShiftTemplateResponse,
    ShiftTemplateUpdateRequest,
    SubstituteRequestCreate,
    SubstituteRequestListResponse,
    SubstituteRequestResponse,
    SubstituteRequestStatus,
)
from app.services.schedule import (
    CalendarOccurrence,
    DailyScheduleConflictError,
    DailyScheduleNotFoundError,
    InvalidScheduleWorkerError,
    ScheduleAssignmentNotFoundError,
    ScheduleService,
    ScheduleWorker,
    ShiftTemplateNotFoundError,
    SubstitutePastDateError,
    SubstituteRequestConflictError,
    SubstituteRequestForbiddenError,
    SubstituteRequestNotFoundError,
    SubstituteTargetConflictError,
)
from app.services.schedule_history import template_on
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError, StoreAccessService

router = APIRouter(prefix="/stores/{store_id}", tags=["schedules"])


def get_schedule_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ScheduleService:
    memberships = MembershipRepository(session)
    return ScheduleService(
        ScheduleRepository(session),
        StoreAccessService(StoreRepository(session), memberships),
        change_recorder=ScheduleChangeRepository(session),
    )


def _error(status_code: int, code: str, message: str) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "detail": None},
    )


@contextmanager
def _translate_access() -> Iterator[None]:
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


def _time_text(value) -> str:
    return value.strftime("%H:%M")


def _template_response(item: ShiftTemplate) -> ShiftTemplateResponse:
    return ShiftTemplateResponse(
        template_id=item.id,
        name=item.name,
        start=_time_text(item.start_time),
        end=_time_text(item.end_time),
        role=item.role,
        headcount=item.headcount,
        sort_order=item.sort_order,
    )


def _worker_response(item: ScheduleWorker) -> ScheduleWorkerResponse:
    return ScheduleWorkerResponse(
        user_id=item.user_id,
        member_id=item.member_id,
        name=item.name,
        role=item.role,
    )


def _worker(workers: dict[UUID, ScheduleWorker], user_id: UUID) -> ScheduleWorker:
    return workers.get(
        user_id,
        ScheduleWorker(
            user_id=user_id,
            member_id=None,
            name="퇴사한 직원",
            role="staff",
        ),
    )


def _assignment_response(
    item: ScheduleAssignment,
    workers: dict[UUID, ScheduleWorker],
) -> ScheduleAssignmentResponse:
    return ScheduleAssignmentResponse(
        assignment_id=item.id,
        template=_template_response(item.template),
        weekday=item.weekday,
        assignee=_worker_response(_worker(workers, item.assignee_user_id)),
    )


def _request_response(
    item: SubstituteRequest,
    workers: dict[UUID, ScheduleWorker],
) -> SubstituteRequestResponse:
    template = template_on(item.assignment.template, item.work_date)
    return SubstituteRequestResponse(
        request_id=item.id,
        status=cast(SubstituteRequestStatus, item.status),
        date=item.work_date,
        assignment_id=item.schedule_assignment_id,
        shift_name=template.name,
        start=_time_text(template.start_time),
        end=_time_text(template.end_time),
        requester=_worker_response(_worker(workers, item.requester_user_id)),
        target=_worker_response(_worker(workers, item.target_user_id)),
        is_read=item.target_read_at is not None,
        created_at=item.created_at,
        responded_at=item.responded_at,
    )


def _calendar_shift_response(
    item: CalendarOccurrence,
    workers: dict[UUID, ScheduleWorker],
) -> CalendarShiftResponse:
    return CalendarShiftResponse(
        assignment_id=item.assignment_id,
        daily_shift_id=item.daily_shift_id,
        template_id=item.template.id,
        date=item.work_date,
        name=item.template.name,
        start=_time_text(item.start_time),
        end=_time_text(item.end_time),
        role=item.template.role,
        assignee=_worker_response(_worker(workers, item.assignee_user_id)),
        substituted=item.substituted,
        manually_adjusted=item.manually_adjusted,
    )


@router.get("/schedule-workers", response_model=ScheduleWorkerListResponse)
async def list_schedule_workers(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> ScheduleWorkerListResponse:
    with _translate_access():
        workers = await service.workers(store_id, user.id)
    return ScheduleWorkerListResponse(
        workers=[_worker_response(item) for item in workers]
    )


@router.post(
    "/shift-templates",
    response_model=ShiftTemplateResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_shift_template(
    store_id: UUID,
    request: ShiftTemplateCreateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> ShiftTemplateResponse:
    with _translate_access():
        item = await service.create_template(store_id, user.id, request)
    return _template_response(item)


@router.get("/shift-templates", response_model=ShiftTemplateListResponse)
async def list_shift_templates(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> ShiftTemplateListResponse:
    with _translate_access():
        items = await service.list_templates(store_id, user.id)
    return ShiftTemplateListResponse(
        templates=[_template_response(item) for item in items]
    )


@router.patch("/shift-templates/{template_id}", response_model=ShiftTemplateResponse)
async def update_shift_template(
    store_id: UUID,
    template_id: UUID,
    request: ShiftTemplateUpdateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> ShiftTemplateResponse | JSONResponse:
    try:
        with _translate_access():
            item = await service.update_template(
                store_id, template_id, user.id, request
            )
    except ShiftTemplateNotFoundError:
        return _error(404, "SHIFT_TEMPLATE_NOT_FOUND", "근무 템플릿을 찾을 수 없어요")
    except ValueError:
        return _error(
            422, "INVALID_SHIFT_TIME", "종료 시간은 시작 시간보다 늦어야 해요"
        )
    return _template_response(item)


@router.delete("/shift-templates/{template_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_shift_template(
    store_id: UUID,
    template_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> Response:
    try:
        with _translate_access():
            await service.delete_template(store_id, template_id, user.id)
    except ShiftTemplateNotFoundError:
        raise HTTPException(
            status_code=404, detail="Shift template not found"
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/fixed-schedule", response_model=ScheduleResponse)
async def replace_schedule(
    store_id: UUID,
    request: ScheduleReplaceRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> ScheduleResponse | JSONResponse:
    try:
        with _translate_access():
            await service.replace_schedule(store_id, user.id, request.assignments)
            items, workers = await service.schedule(store_id, user.id)
    except ShiftTemplateNotFoundError:
        return _error(
            422, "INVALID_SHIFT_TEMPLATE", "다른 매장의 템플릿이 포함되어 있어요"
        )
    except InvalidScheduleWorkerError:
        return _error(
            422, "INVALID_SCHEDULE_WORKER", "배정할 수 없는 구성원이 포함되어 있어요"
        )
    return ScheduleResponse(
        assignments=[_assignment_response(item, workers) for item in items]
    )


@router.get("/fixed-schedule", response_model=ScheduleResponse)
async def get_schedule(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> ScheduleResponse:
    with _translate_access():
        items, workers = await service.schedule(store_id, user.id)
    return ScheduleResponse(
        assignments=[_assignment_response(item, workers) for item in items]
    )


@router.get("/schedule-calendar", response_model=ScheduleCalendarResponse)
async def get_schedule_calendar(
    store_id: UUID,
    start_date: Annotated[date, Query(alias="startDate")],
    end_date: Annotated[date, Query(alias="endDate")],
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> ScheduleCalendarResponse | JSONResponse:
    try:
        with _translate_access():
            occurrences, workers = await service.calendar(
                store_id, user.id, start_date, end_date
            )
    except ValueError:
        return _error(
            422,
            "INVALID_CALENDAR_PERIOD",
            "조회 기간은 시작일부터 최대 63일까지 가능해요",
        )
    return ScheduleCalendarResponse(
        start_date=start_date,
        end_date=end_date,
        shifts=[_calendar_shift_response(item, workers) for item in occurrences],
    )


@router.put(
    "/schedule-calendar/{work_date}",
    response_model=DailyScheduleResponse,
)
async def replace_daily_schedule(
    store_id: UUID,
    work_date: date,
    request: DailyScheduleReplaceRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> DailyScheduleResponse | JSONResponse:
    try:
        with _translate_access():
            override, workers = await service.replace_daily_schedule(
                store_id,
                user.id,
                work_date,
                request.shifts,
            )
    except ShiftTemplateNotFoundError:
        return _error(
            422, "INVALID_SHIFT_TEMPLATE", "다른 매장의 템플릿이 포함되어 있어요"
        )
    except InvalidScheduleWorkerError:
        return _error(
            422, "INVALID_SCHEDULE_WORKER", "배정할 수 없는 구성원이 포함되어 있어요"
        )
    except DailyScheduleConflictError:
        return _error(
            409,
            "DAILY_SCHEDULE_TIME_CONFLICT",
            "같은 구성원의 근무 시간이 겹쳐요",
        )
    return DailyScheduleResponse(
        date=work_date,
        shifts=[
            _calendar_shift_response(
                CalendarOccurrence(
                    assignment_id=None,
                    daily_shift_id=shift.id,
                    template=template_on(shift.template, work_date),
                    start_time=shift.start_time
                    or template_on(shift.template, work_date).start_time,
                    end_time=shift.end_time
                    or template_on(shift.template, work_date).end_time,
                    work_date=work_date,
                    assignee_user_id=shift.assignee_user_id,
                    substituted=False,
                    manually_adjusted=True,
                ),
                workers,
            )
            for shift in override.shifts
        ],
    )


@router.delete(
    "/schedule-calendar/{work_date}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def reset_daily_schedule(
    store_id: UUID,
    work_date: date,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> Response:
    try:
        with _translate_access():
            await service.reset_daily_schedule(store_id, user.id, work_date)
    except DailyScheduleNotFoundError:
        return _error(
            404,
            "DAILY_SCHEDULE_NOT_FOUND",
            "해당 날짜에 저장된 직접 조정 내역이 없어요",
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/substitute-requests",
    response_model=SubstituteRequestResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_substitute_request(
    store_id: UUID,
    request: SubstituteRequestCreate,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> SubstituteRequestResponse | JSONResponse:
    try:
        with _translate_access():
            item, workers = await service.create_substitute_request(
                store_id,
                user.id,
                request.assignment_id,
                request.date,
                request.target_user_id,
            )
    except ScheduleAssignmentNotFoundError:
        return _error(404, "SHIFT_NOT_FOUND", "해당 날짜의 근무를 찾을 수 없어요")
    except InvalidScheduleWorkerError:
        return _error(422, "INVALID_SUBSTITUTE", "대타로 지정할 수 없는 사용자예요")
    except SubstitutePastDateError:
        return _error(422, "PAST_SHIFT", "지난 근무에는 대타를 요청할 수 없어요")
    except SubstituteRequestForbiddenError:
        return _error(403, "NOT_ASSIGNEE", "현재 근무자만 대타를 요청할 수 있어요")
    except SubstituteRequestConflictError:
        return _error(
            409, "SUBSTITUTE_REQUEST_CONFLICT", "이미 진행 중인 대타 요청이 있어요"
        )
    except SubstituteTargetConflictError:
        return _error(409, "SUBSTITUTE_TIME_CONFLICT", "상대방의 근무 시간이 겹쳐요")
    return _request_response(item, workers)


@router.get("/substitute-requests", response_model=SubstituteRequestListResponse)
async def list_substitute_requests(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
    box: Annotated[Literal["received", "sent"], Query()] = "received",
    request_status: Annotated[
        SubstituteRequestStatus | None, Query(alias="status")
    ] = None,
) -> SubstituteRequestListResponse:
    with _translate_access():
        items, workers = await service.list_substitute_requests(
            store_id, user.id, box, request_status
        )
    return SubstituteRequestListResponse(
        requests=[_request_response(item, workers) for item in items]
    )


@router.post(
    "/substitute-requests/{request_id}/accept",
    response_model=SubstituteRequestResponse,
)
async def accept_substitute_request(
    store_id: UUID,
    request_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> SubstituteRequestResponse | JSONResponse:
    return await _respond(store_id, request_id, user.id, service, accept=True)


@router.post(
    "/substitute-requests/{request_id}/reject",
    response_model=SubstituteRequestResponse,
)
async def reject_substitute_request(
    store_id: UUID,
    request_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ScheduleService, Depends(get_schedule_service)],
) -> SubstituteRequestResponse | JSONResponse:
    return await _respond(store_id, request_id, user.id, service, accept=False)


async def _respond(
    store_id: UUID,
    request_id: UUID,
    user_id: UUID,
    service: ScheduleService,
    *,
    accept: bool,
) -> SubstituteRequestResponse | JSONResponse:
    try:
        with _translate_access():
            item, workers = await service.respond_substitute_request(
                store_id, request_id, user_id, accept=accept
            )
    except SubstituteRequestNotFoundError:
        return _error(404, "SUBSTITUTE_REQUEST_NOT_FOUND", "대타 요청을 찾을 수 없어요")
    except SubstituteRequestForbiddenError:
        return _error(403, "NOT_SUBSTITUTE_TARGET", "요청받은 사람만 응답할 수 있어요")
    except SubstituteRequestConflictError:
        return _error(
            409, "SUBSTITUTE_REQUEST_CONFLICT", "이미 처리됐거나 근무자가 변경됐어요"
        )
    except InvalidScheduleWorkerError:
        return _error(422, "INVALID_SUBSTITUTE", "현재 대타를 맡을 수 없는 사용자예요")
    except SubstituteTargetConflictError:
        return _error(
            409, "SUBSTITUTE_TIME_CONFLICT", "현재 근무 시간과 겹쳐 수락할 수 없어요"
        )
    return _request_response(item, workers)
