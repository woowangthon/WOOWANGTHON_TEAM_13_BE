from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from typing import Any, Protocol


class LLMError(Exception):
    """LLM 호출이 실패했거나 응답을 해석할 수 없을 때 발생합니다."""


@dataclass(frozen=True, slots=True)
class LLMImage:
    """LLM에 함께 보내는 이미지입니다."""

    mime_type: str
    data: bytes


class LLMClient(Protocol):
    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Mapping[str, Any],
        images: Sequence[LLMImage] = (),
    ) -> Mapping[str, Any]: ...
