import logging
from collections import Counter
from collections.abc import Iterable, Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal, Protocol
from uuid import UUID, uuid4

from app.integrations.storage import FileStorage, StorageError
from app.models.recipe import Recipe
from app.schemas.recipe import RecipeCreateRequest, RecipeUpdateRequest
from app.services.store_access import StoreAccessProtocol

logger = logging.getLogger(__name__)

ImageSlot = Literal["menu", "recipe"]
IMAGE_SLOTS: tuple[ImageSlot, ...] = ("menu", "recipe")
IMAGE_FIELDS: dict[ImageSlot, str] = {
    "menu": "image_path",
    "recipe": "recipe_image_path",
}
MAX_IMAGE_BYTES = 10 * 1024 * 1024
SIGNED_URL_SECONDS = 6 * 60 * 60
JPEG_SIGNATURE = bytes.fromhex("ffd8ff")
PNG_SIGNATURE = bytes.fromhex("89504e470d0a1a0a")


class RecipeNotFoundError(Exception):
    """매장에서 레시피를 찾지 못했을 때 발생합니다."""


class RecipeImageTooLargeError(Exception):
    """사진이 비어 있거나 10MB를 넘을 때 발생합니다."""


class RecipeImageTypeError(Exception):
    """JPEG, PNG, WebP가 아닌 사진일 때 발생합니다."""


class RecipeImageStorageError(Exception):
    """사진 저장소를 사용할 수 없을 때 발생합니다."""


@dataclass(frozen=True, slots=True)
class RecipeImage:
    """요청으로 받은 사진 내용입니다."""

    data: bytes


def detect_image_type(data: bytes) -> tuple[str, str]:
    """파일 앞부분으로 실제 사진 형식과 확장자를 판별합니다."""
    if data.startswith(JPEG_SIGNATURE):
        return "image/jpeg", "jpg"
    if data.startswith(PNG_SIGNATURE):
        return "image/png", "png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "image/webp", "webp"
    raise RecipeImageTypeError


def image_paths(recipes: Iterable[Recipe]) -> list[str]:
    """레시피들에 저장된 사진 경로를 모읍니다."""
    return [
        path
        for recipe in recipes
        for path in (recipe.image_path, recipe.recipe_image_path)
        if path
    ]


class RecipeRepositoryProtocol(Protocol):
    async def create(self, recipe: Recipe) -> Recipe: ...

    async def list_by_store_id(self, store_id: UUID) -> list[Recipe]: ...

    async def get_by_id_and_store_id(
        self,
        recipe_id: UUID,
        store_id: UUID,
    ) -> Recipe | None: ...

    async def save(self, recipe: Recipe) -> Recipe: ...


def _check_image(image: RecipeImage) -> tuple[bytes, str, str]:
    """사진 크기와 실제 형식을 검사합니다."""
    if not image.data or len(image.data) > MAX_IMAGE_BYTES:
        raise RecipeImageTooLargeError
    content_type, extension = detect_image_type(image.data)
    return image.data, content_type, extension


def _image_path(store_id: UUID, recipe_id: UUID, slot: ImageSlot, ext: str) -> str:
    """매장과 레시피별로 겹치지 않는 사진 경로를 만듭니다."""
    return f"stores/{store_id}/recipes/{recipe_id}/{slot}-{uuid4().hex}.{ext}"


def count_categories(recipes: list[Recipe]) -> dict[str, int]:
    """레시피가 처음 등장한 순서대로 카테고리별 개수를 셉니다."""
    return dict(Counter(recipe.category for recipe in recipes))


class RecipeService:
    def __init__(
        self,
        repository: RecipeRepositoryProtocol,
        store_access: StoreAccessProtocol,
        storage: FileStorage,
    ) -> None:
        """레시피 비즈니스 로직에 사용할 저장소, 권한 검사기, 파일 저장소를 받습니다."""
        self._repository = repository
        self._store_access = store_access
        self._storage = storage

    async def _get_recipe(self, store_id: UUID, recipe_id: UUID) -> Recipe:
        """매장의 레시피를 조회하고 없으면 예외를 발생시킵니다."""
        recipe = await self._repository.get_by_id_and_store_id(recipe_id, store_id)
        if recipe is None:
            raise RecipeNotFoundError
        return recipe

    async def create(
        self,
        store_id: UUID,
        user_id: UUID,
        request: RecipeCreateRequest,
        images: Mapping[ImageSlot, RecipeImage] | None = None,
    ) -> Recipe:
        """매장의 레시피를 사진과 함께 등록합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        checked = {slot: _check_image(image) for slot, image in (images or {}).items()}
        recipe = Recipe(
            id=uuid4(),
            store_id=store_id,
            **request.model_dump(by_alias=False),
        )
        uploaded: list[str] = []
        try:
            for slot, (data, content_type, extension) in checked.items():
                path = _image_path(store_id, recipe.id, slot, extension)
                await self._upload(path, data, content_type)
                uploaded.append(path)
                setattr(recipe, IMAGE_FIELDS[slot], path)
            return await self._repository.create(recipe)
        except BaseException:
            await self._remove_files(uploaded)
            raise

    async def set_image(
        self,
        store_id: UUID,
        recipe_id: UUID,
        user_id: UUID,
        slot: ImageSlot,
        image: RecipeImage,
    ) -> Recipe:
        """레시피의 사진 한 장을 새 사진으로 바꿉니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        data, content_type, extension = _check_image(image)
        recipe = await self._get_recipe(store_id, recipe_id)
        field = IMAGE_FIELDS[slot]
        previous: str | None = getattr(recipe, field)
        path = _image_path(store_id, recipe.id, slot, extension)
        await self._upload(path, data, content_type)
        setattr(recipe, field, path)
        try:
            saved = await self._repository.save(recipe)
        except BaseException:
            await self._remove_files([path])
            raise
        await self._remove_files([previous] if previous else [])
        return saved

    async def remove_image(
        self,
        store_id: UUID,
        recipe_id: UUID,
        user_id: UUID,
        slot: ImageSlot,
    ) -> Recipe:
        """레시피의 사진 한 장을 뺍니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        recipe = await self._get_recipe(store_id, recipe_id)
        field = IMAGE_FIELDS[slot]
        previous: str | None = getattr(recipe, field)
        if previous is None:
            return recipe
        setattr(recipe, field, None)
        saved = await self._repository.save(recipe)
        await self._remove_files([previous])
        return saved

    async def image_urls(self, recipes: Iterable[Recipe]) -> dict[str, str]:
        """레시피 사진의 시간 제한 주소를 한 번에 발급합니다."""
        paths = image_paths(recipes)
        if not paths:
            return {}
        try:
            return await self._storage.signed_urls(paths, SIGNED_URL_SECONDS)
        except StorageError:
            logger.warning("레시피 사진 주소를 발급하지 못했습니다", exc_info=True)
            return {}

    async def _upload(self, path: str, data: bytes, content_type: str) -> None:
        """사진을 올리고 저장소 오류를 도메인 예외로 바꿉니다."""
        try:
            await self._storage.upload(path, data, content_type)
        except StorageError as exc:
            raise RecipeImageStorageError from exc

    async def _remove_files(self, paths: list[str]) -> None:
        """더 이상 쓰지 않는 사진을 지우고 실패해도 요청은 계속합니다."""
        if not paths:
            return
        try:
            await self._storage.delete(paths)
        except StorageError:
            logger.warning("쓰지 않는 레시피 사진을 지우지 못했습니다", exc_info=True)

    async def list_for_store(self, store_id: UUID, user_id: UUID) -> list[Recipe]:
        """매장의 레시피 목록을 조회합니다."""
        await self._store_access.ensure_member(store_id, user_id)
        return await self._repository.list_by_store_id(store_id)

    async def get(self, store_id: UUID, recipe_id: UUID, user_id: UUID) -> Recipe:
        """매장의 레시피 상세 정보를 조회합니다."""
        await self._store_access.ensure_member(store_id, user_id)
        return await self._get_recipe(store_id, recipe_id)

    async def update(
        self,
        store_id: UUID,
        recipe_id: UUID,
        user_id: UUID,
        request: RecipeUpdateRequest,
    ) -> Recipe:
        """매장의 레시피를 수정합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        recipe = await self._get_recipe(store_id, recipe_id)
        fields: Mapping[str, Any] = request.model_dump(
            exclude_unset=True,
            by_alias=False,
        )
        for field, value in fields.items():
            setattr(recipe, field, value)
        return await self._repository.save(recipe)

    async def delete(self, store_id: UUID, recipe_id: UUID, user_id: UUID) -> None:
        """매장의 레시피를 삭제 처리합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        recipe = await self._get_recipe(store_id, recipe_id)
        recipe.deleted_at = datetime.now(UTC)
        await self._repository.save(recipe)
