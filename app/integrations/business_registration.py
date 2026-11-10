from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from typing import Any
from urllib.parse import unquote

import httpx

NTS_VALIDATE_URL = "https://api.odcloud.kr/api/nts-businessman/v1/validate"


class BusinessRegistrationAPIError(Exception):
    """국세청 사업자등록정보 API 호출 또는 응답 처리 실패입니다."""


class BusinessRegistrationConfigurationError(BusinessRegistrationAPIError):
    """국세청 API 인증키가 설정되지 않았습니다."""


@dataclass(frozen=True, slots=True)
class BusinessRegistrationValidationResult:
    valid: bool
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

    async def validate(
        self,
        *,
        business_registration_number: str,
        owner_name: str,
        business_start_date: date,
    ) -> BusinessRegistrationValidationResult:
        """사업자등록번호, 대표자명, 개업일자의 진위 여부를 확인합니다."""
        if not self._api_key:
            raise BusinessRegistrationConfigurationError

        payload = {
            "businesses": [
                {
                    "b_no": business_registration_number,
                    "start_dt": business_start_date.strftime("%Y%m%d"),
                    "p_nm": owner_name,
                }
            ]
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.post(
                    NTS_VALIDATE_URL,
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
    ) -> BusinessRegistrationValidationResult:
        data = payload.get("data")
        if not isinstance(data, list) or not data:
            raise BusinessRegistrationAPIError

        result = data[0]
        if not isinstance(result, Mapping):
            raise BusinessRegistrationAPIError

        valid_code = result.get("valid")
        if valid_code not in {"01", "02"}:
            raise BusinessRegistrationAPIError

        message = result.get("valid_msg")
        if not isinstance(message, str) or not message.strip():
            message = "일치" if valid_code == "01" else "확인할 수 없습니다"
        return BusinessRegistrationValidationResult(
            valid=valid_code == "01",
            message=message.strip()[:500],
        )
