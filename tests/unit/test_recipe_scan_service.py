from collections.abc import Mapping, Sequence
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.integrations.llm import LLMError, LLMImage
from app.services.recipe_scan import (
    MAX_IMAGE_BYTES,
    SCAN_RESPONSE_SCHEMA,
    SCAN_SYSTEM_PROMPT,
    RecipeImageSizeError,
    RecipeImageTypeError,
    RecipeImageUnreadableError,
    RecipeScanIngredientDraft,
    RecipeScanService,
    interpret_scan,
)
from app.services.store import StoreNotFoundError

STORE_ID = uuid4()
OWNER_ID = uuid4()
VALID_RESULT: dict[str, Any] = {
    "isRecipe": True,
    "name": " 딸기라떼 ",
    "category": "라떼",
    "temp": "ICE",
    "size": "16oz",
    "ingredients": [
        {"name": "우유", "amount": "200ml"},
        {"name": "딸기청", "amount": None},
    ],
    "steps": ["우유를 부어요"],
}


class FakeStoreAccess:
    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        if user_id != OWNER_ID:
            raise StoreNotFoundError

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        await self.ensure_owner(store_id, user_id)


class FakeLLM:
    def __init__(self) -> None:
        self.images: list[LLMImage] = []
        self.calls = 0

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Mapping[str, Any],
        images: Sequence[LLMImage] = (),
    ) -> Mapping[str, Any]:
        self.calls += 1
        self.images = list(images)
        return VALID_RESULT


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def service(llm: FakeLLM) -> RecipeScanService:
    return RecipeScanService(FakeStoreAccess(), llm)


async def test_scan_sends_image_and_returns_draft(
    service: RecipeScanService,
    llm: FakeLLM,
) -> None:
    draft = await service.scan(STORE_ID, OWNER_ID, "image/jpeg", b"photo")

    assert llm.images == [LLMImage(mime_type="image/jpeg", data=b"photo")]
    assert draft.name == "딸기라떼"
    assert draft.ingredients[1] == RecipeScanIngredientDraft("딸기청", None)


async def test_non_owner_cannot_scan(
    service: RecipeScanService,
    llm: FakeLLM,
) -> None:
    with pytest.raises(StoreNotFoundError):
        await service.scan(STORE_ID, uuid4(), "image/jpeg", b"photo")
    assert llm.calls == 0


@pytest.mark.parametrize("content_type", ["application/pdf", "image/gif", None])
async def test_rejects_unsupported_type(
    service: RecipeScanService,
    llm: FakeLLM,
    content_type: str | None,
) -> None:
    with pytest.raises(RecipeImageTypeError):
        await service.scan(STORE_ID, OWNER_ID, content_type, b"photo")
    assert llm.calls == 0


@pytest.mark.parametrize("image", [b"", b"x" * (MAX_IMAGE_BYTES + 1)])
async def test_rejects_empty_or_large_image(
    service: RecipeScanService,
    llm: FakeLLM,
    image: bytes,
) -> None:
    with pytest.raises(RecipeImageSizeError):
        await service.scan(STORE_ID, OWNER_ID, "image/png", image)
    assert llm.calls == 0


@pytest.mark.parametrize(
    "overrides",
    [{"isRecipe": False}, {"name": None}, {"name": "  "}],
)
def test_unreadable_photo_raises_error(overrides: dict[str, Any]) -> None:
    with pytest.raises(RecipeImageUnreadableError):
        interpret_scan({**VALID_RESULT, **overrides})


def test_invalid_llm_result_raises_llm_error() -> None:
    with pytest.raises(LLMError):
        interpret_scan({"name": "딸기라떼"})


def test_cleans_unexpected_values() -> None:
    draft = interpret_scan(
        {
            **VALID_RESULT,
            "temp": "COLD",
            "size": " ",
            "ingredients": [{"name": " "}, "우유", {"name": "얼음", "amount": ""}],
            "steps": ["  ", "섞어요", 3],
        }
    )

    assert draft.temp is None
    assert draft.size is None
    assert draft.ingredients == [RecipeScanIngredientDraft("얼음", None)]
    assert draft.steps == ["섞어요"]


def test_single_recipe_has_no_more_recipes() -> None:
    assert interpret_scan(VALID_RESULT).has_more_recipes is False


@pytest.mark.parametrize(
    ("value", "expected"), [(True, True), (False, False), ("true", False)]
)
def test_has_more_recipes_flag(value: object, expected: bool) -> None:
    draft = interpret_scan({**VALID_RESULT, "hasMoreRecipes": value})

    assert draft.has_more_recipes is expected
    assert draft.name == "딸기라떼"


def test_prompt_forbids_mixing_recipes() -> None:
    assert "섞지 않습니다" in SCAN_SYSTEM_PROMPT
    assert "hasMoreRecipes" in SCAN_RESPONSE_SCHEMA["required"]
