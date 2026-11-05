import json
from collections.abc import Callable

import httpx
import pytest

from app.integrations.gemini import GeminiClient
from app.integrations.llm import LLMError

SCHEMA = {"type": "OBJECT"}


def make_client(
    handler: Callable[[httpx.Request], httpx.Response],
    api_key: str = "test-key",
) -> GeminiClient:
    return GeminiClient(
        api_key=api_key,
        model="test-model",
        timeout_seconds=1,
        transport=httpx.MockTransport(handler),
    )


def gemini_response(text: str) -> httpx.Response:
    return httpx.Response(
        200,
        json={"candidates": [{"content": {"parts": [{"text": text}]}}]},
    )


async def generate(client: GeminiClient) -> object:
    return await client.generate_json(
        system_prompt="system",
        user_prompt="user",
        response_schema=SCHEMA,
    )


async def test_sends_key_in_header_and_requests_json() -> None:
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        return gemini_response('{"answerType": "answered"}')

    result = await generate(make_client(handler))

    request = captured[0]
    body = json.loads(request.content)
    assert result == {"answerType": "answered"}
    assert request.url.path.endswith("/models/test-model:generateContent")
    assert request.headers["x-goog-api-key"] == "test-key"
    assert "test-key" not in str(request.url)
    assert body["systemInstruction"]["parts"][0]["text"] == "system"
    assert body["generationConfig"]["responseMimeType"] == "application/json"
    assert body["generationConfig"]["responseSchema"] == SCHEMA


async def test_ignores_thought_parts() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        parts = [{"text": "생각", "thought": True}, {"text": '{"ok": true}'}]
        return httpx.Response(
            200,
            json={"candidates": [{"content": {"parts": parts}}]},
        )

    assert await generate(make_client(handler)) == {"ok": True}


async def test_missing_key_fails_without_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("request must not be sent")

    with pytest.raises(LLMError):
        await generate(make_client(handler, api_key=""))


@pytest.mark.parametrize(
    "response",
    [
        httpx.Response(500, json={}),
        httpx.Response(200, json={"candidates": []}),
        httpx.Response(200, text="not json"),
        gemini_response("not json"),
        gemini_response("[1, 2]"),
    ],
)
async def test_bad_responses_raise_llm_error(response: httpx.Response) -> None:
    with pytest.raises(LLMError):
        await generate(make_client(lambda request: response))


async def test_timeout_raises_llm_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("timeout", request=request)

    with pytest.raises(LLMError):
        await generate(make_client(handler))
