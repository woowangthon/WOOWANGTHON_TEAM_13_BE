from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.store_photos import get_store_photo_service, router
from app.api.v1.users import get_user_service
from app.app import app
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.user import User
from app.services.image import ImageStorageError, ImageTooLargeError, ImageTypeError
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError

STORE_ID = uuid4()


class StubUserService:
    async def get_or_create(self, identity: AuthenticatedUser) -> User:
        return User(
            id=uuid4(), auth_user_id=uuid4(), nickname="사장님", provider="kakao"
        )


class StubStorePhotoService:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.seen: bytes | None = None

    async def upload(self, store_id: UUID, user_id: UUID, data: bytes) -> str:
        if self.error is not None:
            raise self.error
        self.seen = data
        return "https://public/stores/x/photo-1.jpg"


def make_client() -> tuple[TestClient, StubStorePhotoService]:
    service = StubStorePhotoService()
    test_app = FastAPI()
    test_app.include_router(router)

    def authenticated_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=uuid4(), email=None, role=None, claims={})

    test_app.dependency_overrides[get_current_user] = authenticated_user
    test_app.dependency_overrides[get_user_service] = StubUserService
    test_app.dependency_overrides[get_store_photo_service] = lambda: service
    return TestClient(test_app), service


URL = f"/stores/{STORE_ID}/photo"
FILES = [("image", ("cafe.jpg", b"jpeg-bytes", "image/jpeg"))]


def test_route_is_registered_in_application() -> None:
    assert "/api/v1/stores/{store_id}/photo" in app.openapi()["paths"]


def test_upload_returns_photo_url_only() -> None:
    client, service = make_client()

    response = client.post(URL, files=FILES)

    assert response.status_code == 201
    assert response.json() == {"photoUrl": "https://public/stores/x/photo-1.jpg"}
    assert service.seen == b"jpeg-bytes"


def test_missing_image_is_422() -> None:
    client, _ = make_client()

    assert client.post(URL).status_code == 422


def test_errors() -> None:
    client, service = make_client()
    cases = [
        (StoreAccessForbiddenError(), 403, None),
        (StoreNotFoundError(), 404, None),
        (ImageTooLargeError(), 413, "IMAGE_TOO_LARGE"),
        (ImageTypeError(), 415, "UNSUPPORTED_IMAGE_TYPE"),
        (ImageStorageError(), 503, "STORAGE_UNAVAILABLE"),
    ]

    for error, status_code, code in cases:
        service.error = error
        response = client.post(URL, files=FILES)
        assert response.status_code == status_code
        if code is not None:
            assert response.json()["code"] == code
