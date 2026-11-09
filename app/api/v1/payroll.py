from collections.abc import Iterator
from contextlib import contextmanager
from datetime import time
from decimal import Decimal
from typing import Annotated, Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.membership import MembershipRepository
from app.repositories.payroll import PayrollRepository
from app.repositories.store import StoreRepository
from app.schemas.payroll import (
    PayrollEstimateListResponse,
    PayrollEstimateResponse,
    PayrollEstimateSummary,
    PayrollWeekResponse,
    PayrollWorkDayResponse,
)
from app.services.payroll_estimate import (
    PayrollEstimate,
    PayrollEstimateNotFoundError,
    PayrollEstimateService,
    PayrollStaffOnlyError,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError, StoreAccessService

router = APIRouter(prefix="/stores/{store_id}/payroll", tags=["payroll"])

MonthQuery = Annotated[
    str | None,
    Query(pattern=r"^\d{4}-(0[1-9]|1[0-2])$"),
]


def get_payroll_estimate_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PayrollEstimateService:
    """요청에 사용할 예상 급여 서비스를 생성합니다."""
    store_access = StoreAccessService(
        StoreRepository(session),
        MembershipRepository(session),
    )
    return PayrollEstimateService(PayrollRepository(session), store_access)


def _hours(value: Decimal) -> float:
    """근무시간을 소수 둘째 자리까지 숫자로 바꿉니다."""
    return float(round(value, 2))


def _clock(value: time) -> str:
    """시각을 HH:MM 문자열로 바꿉니다."""
    return value.strftime("%H:%M")


def _summary_fields(estimate: PayrollEstimate) -> dict[str, Any]:
    """목록과 상세에 공통으로 들어가는 급여 필드를 만듭니다."""
    result = estimate.result
    return {
        "estimate_id": estimate.member_id,
        "member_id": estimate.member_id,
        "staff_name": estimate.staff_name,
        "hourly_wage": estimate.hourly_wage,
        "tax_type": estimate.tax_type,
        "hours": _hours(result.hours),
        "base_pay": result.base_pay,
        "weekly_allowance": result.weekly_allowance,
        "gross_pay": result.gross_pay,
        "deduction": result.deduction,
        "net_pay": result.net_pay,
        "weeks": [
            PayrollWeekResponse(
                week_start=week.week_start,
                hours=_hours(week.hours),
                weekly_allowance_eligible=week.weekly_allowance_eligible,
                weekly_allowance=week.weekly_allowance,
            )
            for week in result.weeks
        ],
    }


def _to_response(estimate: PayrollEstimate) -> PayrollEstimateResponse:
    """예상 급여 계산 결과를 상세 응답 형식으로 변환합니다."""
    return PayrollEstimateResponse(
        **_summary_fields(estimate),
        store_id=estimate.store_id,
        month=estimate.month,
        payday=estimate.payday,
        weekly_allowance_enabled=estimate.weekly_allowance_enabled,
        work_days=[
            PayrollWorkDayResponse(
                date=day.work_date,
                start=_clock(day.start),
                end=_clock(day.end),
                hours=_hours(day.hours),
                status=day.status,
            )
            for day in estimate.work_days
        ],
        ai_note=None,
        is_estimate=True,
    )


@contextmanager
def _translate_errors() -> Iterator[None]:
    """예상 급여 도메인 예외를 HTTP 오류로 변환합니다."""
    try:
        yield
    except (StoreNotFoundError, PayrollEstimateNotFoundError):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payroll estimate not found",
        ) from None
    except StoreAccessForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner permission required",
        ) from None
    except PayrollStaffOnlyError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Only staff members have payroll estimates",
        ) from None


@router.get("/estimates/me", response_model=PayrollEstimateResponse)
async def get_my_payroll_estimate(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[
        PayrollEstimateService,
        Depends(get_payroll_estimate_service),
    ],
    month: MonthQuery = None,
) -> PayrollEstimateResponse:
    """확정 스케줄로 계산한 내 한 달 예상 급여를 조회합니다."""
    with _translate_errors():
        estimate = await service.estimate_mine(store_id, user.id, month)
    return _to_response(estimate)


@router.get("/estimates", response_model=PayrollEstimateListResponse)
async def list_payroll_estimates(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[
        PayrollEstimateService,
        Depends(get_payroll_estimate_service),
    ],
    month: MonthQuery = None,
) -> PayrollEstimateListResponse:
    """사장님이 재직 중인 직원별 한 달 예상 급여를 조회합니다."""
    with _translate_errors():
        estimates = await service.list_estimates(store_id, user.id, month)
    return PayrollEstimateListResponse(
        store_id=estimates.store_id,
        month=estimates.month,
        payday=estimates.payday,
        members=[
            PayrollEstimateSummary(**_summary_fields(estimate))
            for estimate in estimates.estimates
        ],
        is_estimate=True,
    )


@router.get("/estimates/{estimate_id}", response_model=PayrollEstimateResponse)
async def get_payroll_estimate(
    store_id: UUID,
    estimate_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[
        PayrollEstimateService,
        Depends(get_payroll_estimate_service),
    ],
    month: MonthQuery = None,
) -> PayrollEstimateResponse:
    """예상 급여 상세를 조회합니다. estimateId는 구성원 ID입니다."""
    with _translate_errors():
        estimate = await service.get_estimate(store_id, user.id, estimate_id, month)
    return _to_response(estimate)
