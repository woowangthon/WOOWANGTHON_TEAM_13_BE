from collections.abc import Mapping
from typing import Any, Protocol


class LLMError(Exception):
    """LLM 호출이 실패했거나 응답을 해석할 수 없을 때 발생합니다."""


class LLMClient(Protocol):
    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any]: ...
