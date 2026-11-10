from typing import Protocol
from uuid import UUID, uuid4

from app.integrations.storage import StorageError
from app.services.image import ImageStorageError, check_image
from app.services.store_access import StoreAccessProtocol


class PublicFileStorage(Protocol):
    async def upload(self, path: str, data: bytes, content_type: str) -> None: ...

    def public_url(self, path: str) -> str: ...


class StorePhotoService:
    def __init__(
        self,
        store_access: StoreAccessProtocol,
        storage: PublicFileStorage,
    ) -> None:
        """매장 사진 업로드에 사용할 권한 검사기와 공개 저장소를 받습니다."""
        self._store_access = store_access
        self._storage = storage

    async def upload(self, store_id: UUID, user_id: UUID, data: bytes) -> str:
        """사장님이 올린 매장 사진을 저장하고 공개 주소를 돌려줍니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        content_type, extension = check_image(data)
        path = f"stores/{store_id}/photo-{uuid4().hex}.{extension}"
        try:
            await self._storage.upload(path, data, content_type)
        except StorageError as exc:
            raise ImageStorageError from exc
        return self._storage.public_url(path)
