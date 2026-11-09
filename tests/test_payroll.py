from datetime import date, time
from decimal import Decimal
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
    PayrollStaffOnlyError,
)
from app.services.store import StoreNotFoundError

STORE_ID = uuid4()
URL = f"/stores/{STORE_ID}/payroll/estimates/me"


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
                hours=Decimal(160) / Decimal(60),
                status="worked",
            )
        ],
        result=PayrollResult(
            hours=Decimal(160) / Decimal(60),
            base_pay=27520,
            weekly_allowance=0,
            gross_pay=27520,
            deduction=910,
            net_pay=26610,
            weeks=[
                PayrollWeek(date(2026, 11, 2), Decimal(160) / Decimal(60), False, 0)
            ],
        ),
    )


class StubPayrollService:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.seen: tuple[UUID, str | None] | None = None

    async def estimate_mine(
        self, store_id: UUID, user_id: UUID, month: str | None
    ) -> PayrollEstimate:
        self.seen = (store_id, month)
        if self.error is not None:
            raise self.error
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


def test_payroll_route_is_registered() -> None:
    assert "/api/v1/stores/{store_id}/payroll/estimates/me" in app.openapi()["paths"]


def test_estimate_returns_camel_case_response() -> None:
    client, service = make_client()

    response = client.get(URL, params={"month": "2026-11"})

    assert response.status_code == 200
    assert service.seen == (STORE_ID, "2026-11")
    assert response.json() == {
        "storeId": str(STORE_ID),
        "month": "2026-11",
        "hourlyWage": 10320,
        "payday": None,
        "taxType": "3.3",
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
        "aiNote": None,
        "isEstimate": True,
    }


def test_month_is_optional() -> None:
    client, service = make_client()

    assert client.get(URL).status_code == 200
    assert service.seen == (STORE_ID, None)


@pytest.mark.parametrize("month", ["2026-13", "2026-1", "202611", "abcd-ef"])
def test_invalid_month_is_422(month: str) -> None:
    client, _ = make_client()

    assert client.get(URL, params={"month": month}).status_code == 422


@pytest.mark.parametrize(
    ("error", "status_code"),
    [(StoreNotFoundError(), 404), (PayrollStaffOnlyError(), 403)],
)
def test_errors_are_translated(error: Exception, status_code: int) -> None:
    client, service = make_client()
    service.error = error

    assert client.get(URL).status_code == status_code
