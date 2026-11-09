from datetime import date, time
from decimal import Decimal
from typing import Any
from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.payroll import get_payroll_estimate_service, router
from app.api.v1.users import get_user_service
from app.app import app
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.user import User
from app.services.payroll import PayrollResult, PayrollWeek
from app.services.payroll_estimate import (
    EstimateWorkDay,
    PayrollEstimate,
    PayrollEstimateList,
    PayrollEstimateNotFoundError,
    PayrollStaffOnlyError,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError

STORE_ID = uuid4()
MEMBER_ID = uuid4()
BASE = f"/stores/{STORE_ID}/payroll/estimates"
HOURS = Decimal(160) / Decimal(60)


class StubUserService:
    async def get_or_create(self, identity: AuthenticatedUser) -> User:
        return User(
            id=uuid4(),
            auth_user_id=uuid4(),
            nickname="알바생",
            email=None,
            provider="kakao",
        )


def make_estimate() -> PayrollEstimate:
    return PayrollEstimate(
        store_id=STORE_ID,
        member_id=MEMBER_ID,
        staff_name="민수",
        month="2026-11",
        hourly_wage=10320,
        payday=None,
        tax_type="3.3",
        weekly_allowance_enabled=True,
        work_days=[
            EstimateWorkDay(
                work_date=date(2026, 11, 2),
                start=time(9, 20),
                end=time(12),
                hours=HOURS,
                status="worked",
            )
        ],
        result=PayrollResult(
            hours=HOURS,
            base_pay=27520,
            weekly_allowance=0,
            gross_pay=27520,
            deduction=910,
            net_pay=26610,
            weeks=[PayrollWeek(date(2026, 11, 2), HOURS, False, 0)],
        ),
    )


SUMMARY: dict[str, Any] = {
    "estimateId": str(MEMBER_ID),
    "memberId": str(MEMBER_ID),
    "staffName": "민수",
    "hourlyWage": 10320,
    "taxType": "3.3",
    "hours": 2.67,
    "basePay": 27520,
    "weeklyAllowance": 0,
    "grossPay": 27520,
    "deduction": 910,
    "netPay": 26610,
    "weeks": [
        {
            "weekStart": "2026-11-02",
            "hours": 2.67,
            "weeklyAllowanceEligible": False,
            "weeklyAllowance": 0,
        }
    ],
}
DETAIL: dict[str, Any] = {
    **SUMMARY,
    "storeId": str(STORE_ID),
    "month": "2026-11",
    "payday": None,
    "weeklyAllowanceEnabled": True,
    "workDays": [
        {
            "date": "2026-11-02",
            "start": "09:20",
            "end": "12:00",
            "hours": 2.67,
            "status": "worked",
        }
    ],
    "aiNote": None,
    "isEstimate": True,
}


class StubPayrollService:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.seen: tuple[Any, ...] | None = None

    def _check(self) -> None:
        if self.error is not None:
            raise self.error

    async def estimate_mine(
        self, store_id: UUID, user_id: UUID, month: str | None
    ) -> PayrollEstimate:
        self.seen = ("me", store_id, month)
        self._check()
        return make_estimate()

    async def list_estimates(
        self, store_id: UUID, user_id: UUID, month: str | None
    ) -> PayrollEstimateList:
        self.seen = ("list", store_id, month)
        self._check()
        return PayrollEstimateList(STORE_ID, "2026-11", 25, [make_estimate()])

    async def get_estimate(
        self, store_id: UUID, user_id: UUID, member_id: UUID, month: str | None
    ) -> PayrollEstimate:
        self.seen = ("detail", store_id, member_id, month)
        self._check()
        return make_estimate()


def make_client() -> tuple[TestClient, StubPayrollService]:
    service = StubPayrollService()
    test_app = FastAPI()
    test_app.include_router(router)

    def authenticated_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=uuid4(), email=None, role=None, claims={})

    test_app.dependency_overrides[get_current_user] = authenticated_user
    test_app.dependency_overrides[get_user_service] = StubUserService
    test_app.dependency_overrides[get_payroll_estimate_service] = lambda: service
    return TestClient(test_app), service


def test_payroll_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores/{store_id}/payroll/estimates/me" in paths
    assert "/api/v1/stores/{store_id}/payroll/estimates" in paths
    assert "/api/v1/stores/{store_id}/payroll/estimates/{estimate_id}" in paths


def test_my_estimate_returns_camel_case_response() -> None:
    client, service = make_client()

    response = client.get(f"{BASE}/me", params={"month": "2026-11"})

    assert response.status_code == 200
    assert service.seen == ("me", STORE_ID, "2026-11")
    assert response.json() == DETAIL


def test_list_returns_member_summaries() -> None:
    client, service = make_client()

    response = client.get(BASE, params={"month": "2026-11"})

    assert response.status_code == 200
    assert service.seen == ("list", STORE_ID, "2026-11")
    assert response.json() == {
        "storeId": str(STORE_ID),
        "month": "2026-11",
        "payday": 25,
        "members": [SUMMARY],
        "isEstimate": True,
    }


def test_detail_uses_member_id_as_estimate_id() -> None:
    client, service = make_client()

    response = client.get(f"{BASE}/{MEMBER_ID}")

    assert response.status_code == 200
    assert service.seen == ("detail", STORE_ID, MEMBER_ID, None)
    assert response.json() == DETAIL


def test_detail_rejects_non_uuid_id() -> None:
    client, _ = make_client()

    assert client.get(f"{BASE}/abc").status_code == 422


@pytest.mark.parametrize("path", ["/me", "", f"/{MEMBER_ID}"])
def test_month_is_optional(path: str) -> None:
    client, service = make_client()

    assert client.get(f"{BASE}{path}").status_code == 200
    assert service.seen is not None and service.seen[-1] is None


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "202611", "abcd-ef"])
@pytest.mark.parametrize("path", ["/me", "", f"/{MEMBER_ID}"])
def test_invalid_month_is_422(path: str, month: str) -> None:
    client, _ = make_client()

    assert client.get(f"{BASE}{path}", params={"month": month}).status_code == 422


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (StoreNotFoundError(), 404),
        (PayrollEstimateNotFoundError(), 404),
        (StoreAccessForbiddenError(), 403),
        (PayrollStaffOnlyError(), 403),
    ],
)
@pytest.mark.parametrize("path", ["/me", "", f"/{MEMBER_ID}"])
def test_errors_are_translated(path: str, error: Exception, status_code: int) -> None:
    client, service = make_client()
    service.error = error

    assert client.get(f"{BASE}{path}").status_code == status_code
