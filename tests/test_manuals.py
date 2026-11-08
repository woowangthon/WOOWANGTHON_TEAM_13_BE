import json
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.manuals import get_manual_service, router
from app.api.v1.users import get_user_service
from app.app import app
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.manual import Manual, ManualCategory
from app.models.user import User
from app.schemas.manual import (
    ManualCategoryCreateRequest,
    ManualCreateRequest,
    ManualUpdateRequest,
)
from app.services.manual import (
    MANUAL_TEMPLATES,
    ManualCategoryNotFoundError,
    ManualNotFoundError,
    ManualTemplate,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError
from app.services.user import InactiveUserError

STORE_ID = uuid4()


class StubUserService:
    def __init__(self) -> None:
        self.inactive = False
        self.user = User(
            id=uuid4(),
            auth_user_id=uuid4(),
            nickname="홍길동",
            email="owner@example.com",
            provider="kakao",
        )

    async def get_or_create(self, identity: AuthenticatedUser) -> User:
        if self.inactive:
            raise InactiveUserError
        return self.user


class StubManualService:
    def __init__(self) -> None:
        self.manual = Manual(
            id=uuid4(),
            store_id=STORE_ID,
            category_id=None,
            icon="wifi",
            title="와이파이",
            body="비밀번호 안내",
            updated_at=datetime.now(UTC),
        )
        self.error: Exception | None = None
        self.deleted = False

    def _raise_if_needed(self) -> None:
        if self.error is not None:
            raise self.error

    async def create_category(
        self,
        store_id: UUID,
        user_id: UUID,
        request: ManualCategoryCreateRequest,
    ) -> ManualCategory:
        self._raise_if_needed()
        return ManualCategory(id=uuid4(), store_id=store_id, name=request.name)

    async def recommend(
        self,
        store_id: UUID,
        user_id: UUID,
        keywords: list[str],
    ) -> list[ManualTemplate]:
        self._raise_if_needed()
        return list(MANUAL_TEMPLATES)

    async def create(
        self,
        store_id: UUID,
        user_id: UUID,
        request: ManualCreateRequest,
    ) -> Manual:
        self._raise_if_needed()
        self.manual.title = request.title
        self.manual.body = request.body
        return self.manual

    async def list_for_store(self, store_id: UUID, user_id: UUID) -> list[Manual]:
        self._raise_if_needed()
        return [self.manual]

    async def get(self, store_id: UUID, manual_id: UUID, user_id: UUID) -> Manual:
        self._raise_if_needed()
        return self.manual

    async def update(
        self,
        store_id: UUID,
        manual_id: UUID,
        user_id: UUID,
        request: ManualUpdateRequest,
    ) -> Manual:
        self._raise_if_needed()
        if request.title is not None:
            self.manual.title = request.title
        return self.manual

    async def delete(self, store_id: UUID, manual_id: UUID, user_id: UUID) -> None:
        self._raise_if_needed()
        self.deleted = True


def make_client() -> tuple[TestClient, StubUserService, StubManualService]:
    user_service = StubUserService()
    manual_service = StubManualService()
    test_app = FastAPI()
    test_app.include_router(router)

    def authenticated_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=uuid4(), email=None, role=None, claims={})

    test_app.dependency_overrides[get_current_user] = authenticated_user
    test_app.dependency_overrides[get_user_service] = lambda: user_service
    test_app.dependency_overrides[get_manual_service] = lambda: manual_service
    return TestClient(test_app), user_service, manual_service


def manuals_url(suffix: str = "") -> str:
    return f"/stores/{STORE_ID}/manuals{suffix}"


def test_manual_routes_are_registered_in_application() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores/{store_id}/manuals" in paths
    assert "/api/v1/stores/{store_id}/manuals/{manual_id}" in paths
    assert "/api/v1/stores/{store_id}/manuals/recommendations" in paths
    assert "/api/v1/stores/{store_id}/manual-categories" in paths


def test_create_manual_from_multipart_json_part() -> None:
    client, _, _ = make_client()

    response = client.post(
        manuals_url(),
        data={"manual": json.dumps({"title": "오픈 순서", "body": "머신 예열"})},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "오픈 순서"
    assert set(body) == {
        "manualId",
        "categoryId",
        "icon",
        "title",
        "body",
        "isNew",
        "updatedAt",
    }


def test_create_manual_rejects_invalid_json_part() -> None:
    client, _, _ = make_client()

    for payload in ("not json", json.dumps({"title": " ", "body": "내용"})):
        response = client.post(manuals_url(), data={"manual": payload})
        assert response.status_code == 422


def test_create_manual_rejects_unknown_icon() -> None:
    client, _, _ = make_client()

    response = client.post(
        manuals_url(),
        data={"manual": json.dumps({"title": "제목", "body": "내용", "icon": "x"})},
    )

    assert response.status_code == 422


def test_create_manual_with_files_is_not_silently_dropped() -> None:
    client, _, _ = make_client()

    response = client.post(
        manuals_url(),
        data={"manual": json.dumps({"title": "제목", "body": "내용"})},
        files=[("files", ("a.pdf", b"data", "application/pdf"))],
    )

    assert response.status_code == 501


def test_create_manual_with_other_store_category_returns_422() -> None:
    client, _, service = make_client()
    service.error = ManualCategoryNotFoundError()

    response = client.post(
        manuals_url(),
        data={"manual": json.dumps({"title": "제목", "body": "내용"})},
    )

    assert response.status_code == 422


def test_list_manuals_returns_wrapper() -> None:
    client, _, _ = make_client()

    response = client.get(manuals_url())

    assert response.status_code == 200
    assert [item["title"] for item in response.json()["manuals"]] == ["와이파이"]


def test_is_new_is_false_after_badge_period() -> None:
    client, _, service = make_client()
    service.manual.updated_at = datetime.now(UTC) - timedelta(days=4)

    response = client.get(manuals_url(f"/{service.manual.id}"))

    assert response.json()["isNew"] is False


def test_get_manual_is_new_when_recently_updated() -> None:
    client, _, service = make_client()

    response = client.get(manuals_url(f"/{service.manual.id}"))

    assert response.status_code == 200
    assert response.json()["isNew"] is True


def test_unknown_manual_returns_404() -> None:
    client, _, service = make_client()
    service.error = ManualNotFoundError()

    response = client.get(manuals_url(f"/{uuid4()}"))

    assert response.status_code == 404


def test_inaccessible_store_returns_404() -> None:
    client, _, service = make_client()
    service.error = StoreNotFoundError()

    response = client.get(manuals_url())

    assert response.status_code == 404
    assert response.json()["detail"] == "Store not found"


def test_staff_write_returns_403() -> None:
    client, _, service = make_client()
    service.error = StoreAccessForbiddenError()

    response = client.delete(manuals_url(f"/{service.manual.id}"))

    assert response.status_code == 403
    assert response.json()["detail"] == "Owner permission required"


def test_withdrawn_user_returns_403() -> None:
    client, user_service, _ = make_client()
    user_service.inactive = True

    response = client.get(manuals_url())

    assert response.status_code == 403


def test_update_manual() -> None:
    client, _, service = make_client()

    response = client.patch(
        manuals_url(f"/{service.manual.id}"),
        json={"title": "새 제목"},
    )

    assert response.status_code == 200
    assert response.json()["title"] == "새 제목"


def test_update_manual_rejects_empty_body_and_null_title() -> None:
    client, _, service = make_client()
    url = manuals_url(f"/{service.manual.id}")

    assert client.patch(url, json={}).status_code == 422
    assert client.patch(url, json={"title": None}).status_code == 422


def test_delete_manual() -> None:
    client, _, service = make_client()

    response = client.delete(manuals_url(f"/{service.manual.id}"))

    assert response.status_code == 204
    assert service.deleted is True


def test_create_manual_category() -> None:
    client, _, _ = make_client()

    response = client.post(
        f"/stores/{STORE_ID}/manual-categories",
        json={"name": "마감 업무"},
    )

    assert response.status_code == 201
    assert response.json()["name"] == "마감 업무"
    assert "categoryId" in response.json()


def test_recommend_manuals_returns_templates() -> None:
    client, _, _ = make_client()

    response = client.post(
        manuals_url("/recommendations"),
        json={"storeType": "CAFE", "keywords": ["마감"]},
    )

    assert response.status_code == 200
    recommendations = response.json()["recommendations"]
    assert len(recommendations) == len(MANUAL_TEMPLATES)
    assert set(recommendations[0]) == {"icon", "title", "body"}
