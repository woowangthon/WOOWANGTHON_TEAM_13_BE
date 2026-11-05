import json
from collections.abc import Mapping
from typing import Any

import httpx

from app.integrations.llm import LLMError

GEMINI_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"


class GeminiClient:
    def __init__(
        self,
        *,
        api_key: str,
        model: str,
        timeout_seconds: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Gemini 호출에 필요한 설정을 받습니다."""
        self._api_key = api_key
        self._model = model
        self._timeout_seconds = timeout_seconds
        self._transport = transport

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
                response = await client.post(
                    f"{GEMINI_BASE_URL}/models/{self._model}:generateContent",
                    headers={"x-goog-api-key": self._api_key},
                    json=payload,
                )
                response.raise_for_status()
                return self._parse_response(response.json())
        except (httpx.HTTPError, ValueError) as exc:
            raise LLMError("Gemini request failed") from exc

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
