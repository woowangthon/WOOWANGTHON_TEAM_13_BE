from typing import Any

import pytest
from pydantic import BaseModel, ValidationError

from app.schemas.manual import (
    MANUAL_BODY_MAX_LENGTH,
    ManualCreateRequest,
    ManualUpdateRequest,
)
from app.schemas.recipe import (
    INGREDIENTS_MAX_COUNT,
    MEMO_MAX_LENGTH,
    STEP_MAX_LENGTH,
    STEPS_MAX_COUNT,
    RecipeCreateRequest,
    RecipeUpdateRequest,
)

INGREDIENT = {"name": "우유", "amount": "200ml"}
RECIPE = {"name": "딸기라떼", "category": "라떼"}


@pytest.mark.parametrize("model", [ManualCreateRequest, ManualUpdateRequest])
def test_manual_body_has_upper_limit(model: type[BaseModel]) -> None:
    model.model_validate({"title": "마감", "body": "가" * MANUAL_BODY_MAX_LENGTH})

    with pytest.raises(ValidationError):
        model.model_validate(
            {"title": "마감", "body": "가" * (MANUAL_BODY_MAX_LENGTH + 1)}
        )


@pytest.mark.parametrize(
    ("field", "at_limit", "over_limit"),
    [
        (
            "ingredients",
            [INGREDIENT] * INGREDIENTS_MAX_COUNT,
            [INGREDIENT] * (INGREDIENTS_MAX_COUNT + 1),
        ),
        ("steps", ["섞어요"] * STEPS_MAX_COUNT, ["섞어요"] * (STEPS_MAX_COUNT + 1)),
        ("steps", ["가" * STEP_MAX_LENGTH], ["가" * (STEP_MAX_LENGTH + 1)]),
        ("memo", "가" * MEMO_MAX_LENGTH, "가" * (MEMO_MAX_LENGTH + 1)),
    ],
)
@pytest.mark.parametrize("model", [RecipeCreateRequest, RecipeUpdateRequest])
def test_recipe_fields_have_upper_limits(
    model: type[BaseModel], field: str, at_limit: Any, over_limit: Any
) -> None:
    model.model_validate({**RECIPE, field: at_limit})

    with pytest.raises(ValidationError):
        model.model_validate({**RECIPE, field: over_limit})
