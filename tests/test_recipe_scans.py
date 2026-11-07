from uuid import UUID, uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.dependencies import get_active_user
from app.api.v1.recipe_scans import get_recipe_scan_service, router
from app.app import app
from app.integrations.llm import LLMError
from app.models.user import User
from app.services.recipe_scan import (
    RecipeImageSizeError,
    RecipeImageTypeError,
    RecipeImageUnreadableError,
    RecipeScanDraft,
    RecipeScanIngredientDraft,
)
from app.services.store import StoreNotFoundError

STORE_ID = uuid4()
URL = f"/stores/{STORE_ID}/recipe-scans"
FILES = {"image": ("recipe.jpg", b"photo", "image/jpeg")}


class StubScanService:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.received: tuple[str | None, bytes] | None = None

    async def scan(
        self,
        store_id: UUID,
        user_id: UUID,
        content_type: str | None,
        image: bytes,
    ) -> RecipeScanDraft:
        if self.error is not None:
            raise self.error
        self.received = (content_type, image)
        return RecipeScanDraft(
            name="딸기라떼",
            category=None,
            temp="ICE",
            size=None,
            ingredients=[RecipeScanIngredientDraft("딸기청", None)],
            steps=["섞어요"],
        )


@pytest.fixture
def service() -> StubScanService:
    return StubScanService()


@pytest.fixture
def client(service: StubScanService) -> TestClient:
    test_app = FastAPI()
    test_app.include_router(router)
    test_app.dependency_overrides[get_active_user] = lambda: User(id=uuid4())
    test_app.dependency_overrides[get_recipe_scan_service] = lambda: service
    return TestClient(test_app)


def test_router_is_registered() -> None:
    paths = app.openapi()["paths"]
    assert "/api/v1/stores/{store_id}/recipe-scans" in paths


def test_scan_returns_camel_case_draft_with_nulls(
    client: TestClient,
    service: StubScanService,
) -> None:
    response = client.post(URL, files=FILES)

    assert response.status_code == 200
    assert response.json() == {
        "name": "딸기라떼",
        "category": None,
        "temp": "ICE",
        "size": None,
        "ingredients": [{"name": "딸기청", "amount": None}],
        "steps": ["섞어요"],
    }
    assert service.received == ("image/jpeg", b"photo")


def test_missing_image_is_422(client: TestClient) -> None:
    assert client.post(URL).status_code == 422


@pytest.mark.parametrize(
    ("error", "status_code"),
    [
        (StoreNotFoundError(), 404),
        (RecipeImageTypeError(), 415),
        (RecipeImageSizeError(), 413),
        (RecipeImageUnreadableError(), 422),
        (LLMError("failed"), 503),
    ],
)
def test_errors_are_translated(
    client: TestClient,
    service: StubScanService,
    error: Exception,
    status_code: int,
) -> None:
    service.error = error
    assert client.post(URL, files=FILES).status_code == status_code
