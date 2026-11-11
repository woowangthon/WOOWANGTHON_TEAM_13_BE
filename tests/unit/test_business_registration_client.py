import json
from collections.abc import Callable

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


async def check_status(client: NTSBusinessRegistrationClient) -> object:
    return await client.check_status(
        business_registration_number="1234567890",
    )


async def test_sends_official_nts_status_contract() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return httpx.Response(
            200,
            json={"data": [{"b_stt_cd": "01", "b_stt": "계속사업자"}]},
        )

    result = await check_status(make_client(handler, api_key="encoded%2Bkey"))

    request = captured[0]
    assert request.method == "POST"
    assert request.url.path.endswith("/nts-businessman/v1/status")
    assert request.url.params["serviceKey"] == "encoded+key"
    assert json.loads(request.content) == {"b_no": ["1234567890"]}
    assert result.active is True
    assert result.message == "계속사업자"


async def test_maps_closed_business_to_invalid_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={"data": [{"b_stt_cd": "03", "b_stt": "폐업자"}]},
        )

    result = await check_status(make_client(handler))

    assert result.active is False
    assert result.message == "폐업자"


async def test_maps_unregistered_number_to_invalid_result() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "data": [
                    {
                        "b_stt_cd": "",
                        "b_stt": "",
                        "tax_type": "국세청에 등록되지 않은 사업자등록번호입니다",
                    }
                ]
            },
        )

    result = await check_status(make_client(handler))

    assert result.active is False
    assert result.message == "국세청에 등록되지 않은 사업자등록번호입니다"


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={}),
        httpx.Response(200, json={}),
        httpx.Response(200, json={"data": []}),
        httpx.Response(200, json={"data": [{"b_stt_cd": "99"}]}),
        httpx.Response(200, text="not-json"),
    ],
)
async def test_rejects_provider_failures(response: httpx.Response) -> None:
    with pytest.raises(BusinessRegistrationAPIError):
        await check_status(make_client(lambda request: response))


async def test_missing_key_fails_without_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("request must not be sent")

    with pytest.raises(BusinessRegistrationConfigurationError):
        await check_status(make_client(handler, api_key=""))
