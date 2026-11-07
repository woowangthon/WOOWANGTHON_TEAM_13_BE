import asyncio
import json
from collections.abc import Mapping
from typing import Any

import httpx

from app.integrations.llm import LLMError

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
RETRYABLE_STATUS_CODES = frozenset({429, 503})
RETRY_DELAY_SECONDS = 1.0


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
        retry_delay_seconds: float = RETRY_DELAY_SECONDS,
    ) -> None:
        """Gemini 호출에 필요한 설정을 받습니다."""
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._transport = transport
        self._retry_delay_seconds = retry_delay_seconds

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Gemini에 구조화된 JSON 응답을 요청합니다."""
        if not self._api_key:
            raise LLMError("Gemini API key is not configured")

        payload = {
            "systemInstruction": {"parts": [{"text": system_prompt}]},
            "contents": [{"role": "user", "parts": [{"text": user_prompt}]}],
            "generationConfig": {
                "responseMimeType": "application/json",
                "responseSchema": response_schema,
            },
        }
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await self._post(client, payload)
                if response.status_code in RETRYABLE_STATUS_CODES:
                    await asyncio.sleep(self._retry_delay_seconds)
                    response = await self._post(client, payload)
                response.raise_for_status()
                return self._parse_response(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMError("Gemini request failed") from exc

    async def _post(
        self,
        client: httpx.AsyncClient,
        payload: Mapping[str, Any],
    ) -> httpx.Response:
        """Gemini에 생성 요청을 한 번 보냅니다."""
        return await client.post(
            f"{GEMINI_BASE_URL}/models/{self._model}:generateContent",
            headers={"x-goog-api-key": self._api_key},
            json=payload,
        )

    @staticmethod
    def _parse_response(data: Mapping[str, Any]) -> Mapping[str, Any]:
        """Gemini 응답에서 JSON 본문을 꺼냅니다."""
        try:
            parts = data["candidates"][0]["content"]["parts"]
            text = "".join(
                part["text"]
                for part in parts
                if "text" in part and not part.get("thought")
            )
        except (KeyError, IndexError, TypeError) as exc:
            raise LLMError("Gemini response has no content") from exc

        result = json.loads(text)
        if not isinstance(result, Mapping):
            raise LLMError("Gemini response is not a JSON object")
        return result
