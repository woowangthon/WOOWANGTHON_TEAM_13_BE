import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.recipes import get_recipe_service, router
from app.api.v1.users import get_user_service
from app.app import app
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.recipe import Recipe
from app.models.user import User
from app.schemas.recipe import RecipeCreateRequest, RecipeUpdateRequest
from app.services.recipe import RecipeNotFoundError
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError

STORE_ID = uuid4()
VALID_RECIPE = {
    "name": "딸기라떼",
    "category": "라떼",
    "temp": "ICE",
    "ingredients": [{"name": "우유", "amount": "200ml"}],
    "steps": ["우유를 천천히 부어요"],
}


class StubUserService:
    def __init__(self) -> None:
        self.user = User(
            id=uuid4(),
            auth_user_id=uuid4(),
            nickname="홍길동",
            email="owner@example.com",
            provider="kakao",
        )

    async def get_or_create(self, identity: AuthenticatedUser) -> User:
        return self.user


class StubRecipeService:
    def __init__(self) -> None:
        self.recipe = Recipe(
            id=uuid4(),
            store_id=STORE_ID,
            name="딸기라떼",
            category="라떼",
            temp="ICE",
            size="16oz",
            ingredients=[{"name": "우유", "amount": "200ml"}],
            steps=["우유를 천천히 부어요"],
            memo=None,
            updated_at=datetime.now(UTC),
        )
        self.error: Exception | None = None
        self.deleted = False

    def _raise_if_needed(self) -> None:
        if self.error is not None:
            raise self.error

    async def create(
        self,
        store_id: UUID,
        user_id: UUID,
        request: RecipeCreateRequest,
    ) -> Recipe:
        self._raise_if_needed()
        self.recipe.name = request.name
        return self.recipe

    async def list_for_store(self, store_id: UUID, user_id: UUID) -> list[Recipe]:
        self._raise_if_needed()
        return [self.recipe]

    async def get(self, store_id: UUID, recipe_id: UUID, user_id: UUID) -> Recipe:
        self._raise_if_needed()
        return self.recipe

    async def update(
        self,
        store_id: UUID,
        recipe_id: UUID,
        user_id: UUID,
        request: RecipeUpdateRequest,
    ) -> Recipe:
        self._raise_if_needed()
        if request.name is not None:
            self.recipe.name = request.name
        return self.recipe

    async def delete(self, store_id: UUID, recipe_id: UUID, user_id: UUID) -> None:
        self._raise_if_needed()
        self.deleted = True


def make_client() -> tuple[TestClient, StubRecipeService]:
    user_service = StubUserService()
    recipe_service = StubRecipeService()
    test_app = FastAPI()
    test_app.include_router(router)

    def authenticated_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=uuid4(), email=None, role=None, claims={})

    test_app.dependency_overrides[get_current_user] = authenticated_user
    test_app.dependency_overrides[get_user_service] = lambda: user_service
    test_app.dependency_overrides[get_recipe_service] = lambda: recipe_service
    return TestClient(test_app), recipe_service


def recipes_url(suffix: str = "") -> str:
    return f"/stores/{STORE_ID}/recipes{suffix}"


def test_recipe_routes_are_registered_in_application() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores/{store_id}/recipes" in paths
    assert "/api/v1/stores/{store_id}/recipes/{recipe_id}" in paths


def test_create_recipe_from_multipart_json_part() -> None:
    client, _ = make_client()

    response = client.post(recipes_url(), data={"recipe": json.dumps(VALID_RECIPE)})

    assert response.status_code == 201
    assert set(response.json()) == {
        "recipeId",
        "name",
        "category",
        "temp",
        "size",
        "ingredients",
        "steps",
        "memo",
        "isNew",
        "updatedAt",
    }


def test_create_recipe_rejects_invalid_values() -> None:
    client, _ = make_client()
    invalid_payloads = [
        "not json",
        json.dumps({**VALID_RECIPE, "name": " "}),
        json.dumps({**VALID_RECIPE, "temp": "COLD"}),
        json.dumps({**VALID_RECIPE, "steps": [" "]}),
        json.dumps({**VALID_RECIPE, "ingredients": [{"name": "우유"}]}),
    ]

    for payload in invalid_payloads:
        response = client.post(recipes_url(), data={"recipe": payload})
        assert response.status_code == 422


def test_create_recipe_with_images_is_not_silently_dropped() -> None:
    client, _ = make_client()

    response = client.post(
        recipes_url(),
        data={"recipe": json.dumps(VALID_RECIPE)},
        files=[("images", ("a.jpg", b"data", "image/jpeg"))],
    )

    assert response.status_code == 501


def test_list_recipes_returns_categories_and_summaries() -> None:
    client, _ = make_client()

    response = client.get(recipes_url())

    assert response.status_code == 200
    body = response.json()
    assert body["categories"] == [{"name": "라떼", "count": 1}]
    assert body["defaultCategory"] is None
    assert body["recipes"][0]["ingredients"] == [{"name": "우유", "amount": "200ml"}]
    assert "steps" not in body["recipes"][0]
    assert "memo" not in body["recipes"][0]


def test_get_recipe_includes_steps_and_memo() -> None:
    client, service = make_client()

    response = client.get(recipes_url(f"/{service.recipe.id}"))

    assert response.status_code == 200
    assert response.json()["steps"] == ["우유를 천천히 부어요"]
    assert response.json()["memo"] is None
    assert response.json()["isNew"] is True


def test_is_new_is_false_after_badge_period() -> None:
    client, service = make_client()
    service.recipe.updated_at = datetime.now(UTC) - timedelta(days=4)

    response = client.get(recipes_url(f"/{service.recipe.id}"))

    assert response.json()["isNew"] is False


def test_unknown_recipe_returns_404() -> None:
    client, service = make_client()
    service.error = RecipeNotFoundError()

    response = client.get(recipes_url(f"/{uuid4()}"))

    assert response.status_code == 404


def test_inaccessible_store_returns_404() -> None:
    client, service = make_client()
    service.error = StoreNotFoundError()

    response = client.get(recipes_url())

    assert response.status_code == 404


def test_staff_write_returns_403() -> None:
    client, service = make_client()
    service.error = StoreAccessForbiddenError()

    response = client.delete(recipes_url(f"/{service.recipe.id}"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Owner permission required"


def test_update_recipe() -> None:
    client, service = make_client()

    response = client.patch(
        recipes_url(f"/{service.recipe.id}"),
        json={"name": "새 이름"},
    )

    assert response.status_code == 200
    assert response.json()["name"] == "새 이름"


def test_update_recipe_rejects_empty_and_null_required_fields() -> None:
    client, service = make_client()
    url = recipes_url(f"/{service.recipe.id}")

    assert client.patch(url, json={}).status_code == 422
    assert client.patch(url, json={"name": None}).status_code == 422
    assert client.patch(url, json={"ingredients": None}).status_code == 422
    assert client.patch(url, json={"steps": None}).status_code == 422


def test_delete_recipe() -> None:
    client, service = make_client()

    response = client.delete(recipes_url(f"/{service.recipe.id}"))

    assert response.status_code == 204
    assert service.deleted is True
