import json
from collections.abc import Callable
from datetime import date

import httpx
import pytest

from app.integrations.business_registration import (
    BusinessRegistrationAPIError,
    BusinessRegistrationConfigurationError,
    NTSBusinessRegistrationClient,
)


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    api_key: str = "test-key",
) -> NTSBusinessRegistrationClient:
    return NTSBusinessRegistrationClient(
        api_key=api_key,
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )


async def validate(client: NTSBusinessRegistrationClient) -> object:
    return await client.validate(
        business_registration_number="1234567890",
        owner_name="홍길동",
        business_start_date=date(2026, 1, 15),
    )


async def test_sends_official_nts_validation_contract() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"data": [{"valid": "01", "valid_msg": "확인되었습니다."}]},
        )

    result = await validate(make_client(handler, api_key="encoded%2Bkey"))

    request = captured[0]
    assert request.method == "POST"
    assert request.url.path.endswith("/nts-businessman/v1/validate")
    assert request.url.params["serviceKey"] == "encoded+key"
    assert json.loads(request.content) == {
        "businesses": [
            {
                "b_no": "1234567890",
                "start_dt": "20260115",
                "p_nm": "홍길동",
            }
        ]
    }
    assert result.valid is True
    assert result.message == "확인되었습니다."


async def test_maps_mismatched_information_to_invalid_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"valid": "02", "valid_msg": "확인할 수 없습니다."}]},
        )

    result = await validate(make_client(handler))

    assert result.valid is False
    assert result.message == "확인할 수 없습니다."


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={}),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"data": []}),
        httpx.Response(200, json={"data": [{"valid": "99"}]}),
        httpx.Response(200, text="not-json"),
    ],
)
async def test_rejects_provider_failures(response: httpx.Response) -> None:
    with pytest.raises(BusinessRegistrationAPIError):
        await validate(make_client(lambda request: response))


async def test_missing_key_fails_without_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("request must not be sent")

    with pytest.raises(BusinessRegistrationConfigurationError):
        await validate(make_client(handler, api_key=""))
