from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from datetime import UTC, datetime, timedelta
from typing import Annotated
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Response,
    UploadFile,
    status,
)
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user
from app.core.config import settings
from app.db.session import get_db
from app.integrations.storage import SupabaseStorageClient
from app.models.recipe import Recipe
from app.models.user import User
from app.repositories.membership import MembershipRepository
from app.repositories.recipe import RecipeRepository
from app.repositories.store import StoreRepository
from app.schemas.recipe import (
    RecipeCategorySummary,
    RecipeCreateRequest,
    RecipeIngredient,
    RecipeListResponse,
    RecipeResponse,
    RecipeSummaryResponse,
    RecipeUpdateRequest,
)
from app.services.recipe import (
    MAX_IMAGE_BYTES,
    ImageSlot,
    RecipeImage,
    RecipeImageStorageError,
    RecipeImageTooLargeError,
    RecipeImageTypeError,
    RecipeNotFoundError,
    RecipeService,
    count_categories,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import (
    StoreAccessForbiddenError,
    StoreAccessService,
)

router = APIRouter(prefix="/stores/{store_id}/recipes", tags=["recipes"])

NEW_BADGE_PERIOD = timedelta(days=3)
IMAGE_ERROR_RESPONSES: dict[int | str, dict[str, str]] = {
    status.HTTP_413_CONTENT_TOO_LARGE: {"description": "IMAGE_TOO_LARGE"},
    status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {"description": "UNSUPPORTED_IMAGE_TYPE"},
    status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "STORAGE_UNAVAILABLE"},
}


def get_recipe_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> RecipeService:
    """요청에 사용할 레시피 서비스를 생성합니다."""
    return RecipeService(
        RecipeRepository(session),
        StoreAccessService(
            StoreRepository(session),
            MembershipRepository(session),
        ),
        SupabaseStorageClient(
            supabase_url=settings.supabase_url,
            secret_key=settings.supabase_secret_key,
            bucket=settings.supabase_storage_bucket,
        ),
    )


def _url(urls: Mapping[str, str], path: str | None) -> str | None:
    """사진 경로에 해당하는 시간 제한 주소를 찾습니다."""
    return urls.get(path) if path else None


def _to_summary(recipe: Recipe, urls: Mapping[str, str]) -> RecipeSummaryResponse:
    """레시피 모델을 목록 항목 형식으로 변환합니다."""
    return RecipeSummaryResponse(
        recipe_id=recipe.id,
        name=recipe.name,
        category=recipe.category,
        temp=recipe.temp,
        size=recipe.size,
        ingredients=[RecipeIngredient(**item) for item in recipe.ingredients],
        image_url=_url(urls, recipe.image_path),
        recipe_image_url=_url(urls, recipe.recipe_image_path),
        is_new=datetime.now(UTC) - recipe.updated_at <= NEW_BADGE_PERIOD,
        updated_at=recipe.updated_at,
    )


def _to_response(recipe: Recipe, urls: Mapping[str, str]) -> RecipeResponse:
    """레시피 모델을 상세 응답 형식으로 변환합니다."""
    return RecipeResponse(
        **_to_summary(recipe, urls).model_dump(by_alias=False),
        steps=recipe.steps,
        memo=recipe.memo,
    )


async def _respond(service: RecipeService, recipe: Recipe) -> RecipeResponse:
    """사진 주소를 발급해 레시피 상세 응답을 만듭니다."""
    return _to_response(recipe, await service.image_urls([recipe]))


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """FE와 맞춘 code, message 형식의 오류 응답을 만듭니다."""
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "detail": None},
    )


class _ImageErrorResponse(Exception):
    """사진 오류를 code, message 응답으로 돌려주기 위해 사용합니다."""

    def __init__(self, response: JSONResponse) -> None:
        self.response = response


@contextmanager
def _translate_errors() -> Iterator[None]:
    """레시피 도메인 예외를 HTTP 오류로 변환합니다."""
    try:
        yield
    except StoreNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        ) from None
    except StoreAccessForbiddenError:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Owner permission required",
        ) from None
    except RecipeNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Recipe not found",
        ) from None
    except RecipeImageTooLargeError:
        raise _ImageErrorResponse(
            _error_response(
                status.HTTP_413_CONTENT_TOO_LARGE,
                "IMAGE_TOO_LARGE",
                "10MB 이하 사진만 올릴 수 있어요",
            )
        ) from None
    except RecipeImageTypeError:
        raise _ImageErrorResponse(
            _error_response(
                status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                "UNSUPPORTED_IMAGE_TYPE",
                "JPEG, PNG, WebP 사진만 올릴 수 있어요",
            )
        ) from None
    except RecipeImageStorageError:
        raise _ImageErrorResponse(
            _error_response(
                status.HTTP_503_SERVICE_UNAVAILABLE,
                "STORAGE_UNAVAILABLE",
                "사진을 저장하지 못했어요. 잠시 후 다시 시도해 주세요",
            )
        ) from None


def _parse_recipe_part(recipe: str) -> RecipeCreateRequest:
    """multipart의 recipe JSON 파트를 검증합니다."""
    try:
        return RecipeCreateRequest.model_validate_json(recipe)
    except ValidationError as exc:
        raise RequestValidationError(
            exc.errors(include_url=False, include_context=False)
        ) from None


async def _read_image(file: UploadFile) -> RecipeImage:
    """업로드 파일을 최대 크기보다 1바이트 더 읽어 크기 초과를 판별합니다."""
    return RecipeImage(data=await file.read(MAX_IMAGE_BYTES + 1))


@router.post(
    "",
    response_model=RecipeResponse,
    status_code=status.HTTP_201_CREATED,
    responses=IMAGE_ERROR_RESPONSES,
)
async def create_recipe(
    store_id: UUID,
    recipe: Annotated[str, Form()],
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[RecipeService, Depends(get_recipe_service)],
    image: Annotated[UploadFile | None, File()] = None,
    recipe_image: Annotated[UploadFile | None, File(alias="recipeImage")] = None,
) -> RecipeResponse | JSONResponse:
    """매장의 레시피를 메뉴 사진, 레시피 사진과 함께 등록합니다."""
    request = _parse_recipe_part(recipe)
    images: dict[ImageSlot, RecipeImage] = {}
    if image is not None:
        images["menu"] = await _read_image(image)
    if recipe_image is not None:
        images["recipe"] = await _read_image(recipe_image)
    try:
        with _translate_errors():
            created = await service.create(store_id, user.id, request, images)
    except _ImageErrorResponse as error:
        return error.response
    return await _respond(service, created)


@router.get("", response_model=RecipeListResponse)
async def list_recipes(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[RecipeService, Depends(get_recipe_service)],
) -> RecipeListResponse:
    """매장의 레시피 목록을 카테고리 정보와 함께 조회합니다."""
    with _translate_errors():
        recipes = await service.list_for_store(store_id, user.id)
    urls = await service.image_urls(recipes)
    return RecipeListResponse(
        categories=[
            RecipeCategorySummary(name=name, count=count)
            for name, count in count_categories(recipes).items()
        ],
        default_category=None,
        recipes=[_to_summary(recipe, urls) for recipe in recipes],
    )


@router.get("/{recipe_id}", response_model=RecipeResponse)
async def get_recipe(
    store_id: UUID,
    recipe_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[RecipeService, Depends(get_recipe_service)],
) -> RecipeResponse:
    """매장의 레시피 상세 정보를 조회합니다."""
    with _translate_errors():
        recipe = await service.get(store_id, recipe_id, user.id)
    return await _respond(service, recipe)


@router.patch("/{recipe_id}", response_model=RecipeResponse)
async def update_recipe(
    store_id: UUID,
    recipe_id: UUID,
    request: RecipeUpdateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[RecipeService, Depends(get_recipe_service)],
) -> RecipeResponse:
    """매장의 레시피를 수정합니다."""
    with _translate_errors():
        recipe = await service.update(store_id, recipe_id, user.id, request)
    return await _respond(service, recipe)


@router.put(
    "/{recipe_id}/images/{slot}",
    response_model=RecipeResponse,
    responses=IMAGE_ERROR_RESPONSES,
)
async def set_recipe_image(
    store_id: UUID,
    recipe_id: UUID,
    slot: ImageSlot,
    image: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[RecipeService, Depends(get_recipe_service)],
) -> RecipeResponse | JSONResponse:
    """레시피의 메뉴 사진이나 레시피 사진을 새 사진으로 바꿉니다."""
    content = await _read_image(image)
    try:
        with _translate_errors():
            recipe = await service.set_image(
                store_id,
                recipe_id,
                user.id,
                slot,
                content,
            )
    except _ImageErrorResponse as error:
        return error.response
    return await _respond(service, recipe)


@router.delete(
    "/{recipe_id}/images/{slot}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def delete_recipe_image(
    store_id: UUID,
    recipe_id: UUID,
    slot: ImageSlot,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[RecipeService, Depends(get_recipe_service)],
) -> Response:
    """레시피의 메뉴 사진이나 레시피 사진을 뺍니다."""
    with _translate_errors():
        await service.remove_image(store_id, recipe_id, user.id, slot)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{recipe_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_recipe(
    store_id: UUID,
    recipe_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[RecipeService, Depends(get_recipe_service)],
) -> Response:
    """매장의 레시피를 삭제 처리합니다."""
    with _translate_errors():
        await service.delete(store_id, recipe_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
