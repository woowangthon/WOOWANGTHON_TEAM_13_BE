from uuid import UUID, uuid4

import pytest

from app.integrations.storage import StorageError, SupabaseStorageClient
from app.services.image import (
    MAX_IMAGE_BYTES,
    ImageStorageError,
    ImageTooLargeError,
    ImageTypeError,
    check_image,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError
from app.services.store_photo import StorePhotoService

STORE_ID = uuid4()
OWNER_ID = uuid4()
STAFF_ID = uuid4()
JPEG = bytes.fromhex("ffd8ffe000104a464946") + b"body"
PNG = bytes.fromhex("89504e470d0a1a0a") + b"body"


class FakeStoreAccess:
    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        if store_id != STORE_ID:
            raise StoreNotFoundError
        if user_id == STAFF_ID:
            raise StoreAccessForbiddenError
        if user_id != OWNER_ID:
            raise StoreNotFoundError

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        await self.ensure_owner(store_id, user_id)


class FakePublicStorage:
    def __init__(self) -> None:
        self.files: dict[str, tuple[bytes, str]] = {}
        self.fail = False

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        if self.fail:
            raise StorageError("down")
        self.files[path] = (data, content_type)

    def public_url(self, path: str) -> str:
        return f"https://public/{path}"


@pytest.fixture
def storage() -> FakePublicStorage:
    return FakePublicStorage()


@pytest.fixture
def service(storage: FakePublicStorage) -> StorePhotoService:
    return StorePhotoService(FakeStoreAccess(), storage)


async def test_owner_upload_returns_public_url(
    service: StorePhotoService,
    storage: FakePublicStorage,
) -> None:
    url = await service.upload(STORE_ID, OWNER_ID, PNG)

    [(path, (data, content_type))] = storage.files.items()
    assert path.startswith(f"stores/{STORE_ID}/photo-")
    assert path.endswith(".png")
    assert (data, content_type) == (PNG, "image/png")
    assert url == f"https://public/{path}"


async def test_each_upload_gets_new_path(
    service: StorePhotoService,
    storage: FakePublicStorage,
) -> None:
    first = await service.upload(STORE_ID, OWNER_ID, JPEG)
    second = await service.upload(STORE_ID, OWNER_ID, JPEG)

    assert first != second
    assert len(storage.files) == 2


async def test_staff_and_stranger_cannot_upload(
    service: StorePhotoService,
    storage: FakePublicStorage,
) -> None:
    with pytest.raises(StoreAccessForbiddenError):
        await service.upload(STORE_ID, STAFF_ID, JPEG)
    with pytest.raises(StoreNotFoundError):
        await service.upload(STORE_ID, uuid4(), JPEG)
    assert storage.files == {}


async def test_bad_images_are_rejected_before_upload(
    service: StorePhotoService,
    storage: FakePublicStorage,
) -> None:
    with pytest.raises(ImageTypeError):
        await service.upload(STORE_ID, OWNER_ID, b"GIF89a")
    with pytest.raises(ImageTooLargeError):
        await service.upload(STORE_ID, OWNER_ID, b"")
    with pytest.raises(ImageTooLargeError):
        await service.upload(STORE_ID, OWNER_ID, JPEG + bytes(MAX_IMAGE_BYTES))
    assert storage.files == {}


async def test_storage_failure_is_reported(
    service: StorePhotoService,
    storage: FakePublicStorage,
) -> None:
    storage.fail = True

    with pytest.raises(ImageStorageError):
        await service.upload(STORE_ID, OWNER_ID, JPEG)


def test_check_image_returns_type_and_extension() -> None:
    assert check_image(JPEG) == ("image/jpeg", "jpg")
    assert check_image(PNG) == ("image/png", "png")


def test_public_url_format() -> None:
    client = SupabaseStorageClient(
        supabase_url="https://project.supabase.co/",
        secret_key="key",
        bucket="store-photos",
    )

    assert client.public_url("stores/a/photo-1.jpg") == (
        "https://project.supabase.co/storage/v1/object/public/store-photos/"
        "stores/a/photo-1.jpg"
    )
