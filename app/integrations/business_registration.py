from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import unquote

import httpx

NTS_STATUS_URL = "https://api.odcloud.kr/api/nts-businessman/v1/status"


class BusinessRegistrationAPIError(Exception):
    """국세청 사업자등록정보 API 호출 또는 응답 처리 실패입니다."""


class BusinessRegistrationConfigurationError(BusinessRegistrationAPIError):
    """국세청 API 인증키가 설정되지 않았습니다."""


@dataclass(frozen=True, slots=True)
class BusinessRegistrationStatusResult:
    active: bool
    message: str


class NTSBusinessRegistrationClient:
    def __init__(
        self,
        *,
        api_key: str,
        timeout_seconds: float = 10,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._api_key = unquote(api_key.strip())
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    async def check_status(
        self,
        *,
        business_registration_number: str,
    ) -> BusinessRegistrationStatusResult:
        """사업자등록번호만으로 계속사업자 여부를 확인합니다."""
        if not self._api_key:
            raise BusinessRegistrationConfigurationError

        payload = {"b_no": [business_registration_number]}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    NTS_STATUS_URL,
                    params={"serviceKey": self._api_key},
                    headers={"Accept": "application/json"},
                    json=payload,
                )
                response.raise_for_status()
                return self._parse_response(response.json())
        except BusinessRegistrationAPIError:
            raise
        except (httpx.HTTPError, ValueError, TypeError) as exc:
            raise BusinessRegistrationAPIError from exc

    @staticmethod
    def _parse_response(
        payload: Mapping[str, Any],
    ) -> BusinessRegistrationStatusResult:
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise BusinessRegistrationAPIError

        result = data[0]
        if not isinstance(result, Mapping):
            raise BusinessRegistrationAPIError

        status_code = result.get("b_stt_cd")
        if status_code not in {"", "01", "02", "03"}:
            raise BusinessRegistrationAPIError

        message = result.get("b_stt")
        if not isinstance(message, str) or not message.strip():
            message = result.get("tax_type")
        if not isinstance(message, str) or not message.strip():
            message = "계속사업자" if status_code == "01" else "확인할 수 없습니다"
        return BusinessRegistrationStatusResult(
            active=status_code == "01",
            message=message.strip()[:500],
        )
