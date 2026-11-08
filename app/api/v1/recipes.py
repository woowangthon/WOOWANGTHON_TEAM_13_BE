from collections.abc import Iterator
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
from pydantic import ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user
from app.db.session import get_db
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
from app.services.recipe import RecipeNotFoundError, RecipeService, count_categories
from app.services.store import StoreNotFoundError
from app.services.store_access import (
    StoreAccessForbiddenError,
    StoreAccessService,
)

router = APIRouter(prefix="/stores/{store_id}/recipes", tags=["recipes"])

NEW_BADGE_PERIOD = timedelta(days=3)


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
    )


def _to_summary(recipe: Recipe) -> RecipeSummaryResponse:
    """레시피 모델을 목록 항목 형식으로 변환합니다."""
    return RecipeSummaryResponse(
        recipe_id=recipe.id,
        name=recipe.name,
        category=recipe.category,
        temp=recipe.temp,
        size=recipe.size,
        ingredients=[RecipeIngredient(**item) for item in recipe.ingredients],
        is_new=datetime.now(UTC) - recipe.updated_at <= NEW_BADGE_PERIOD,
        updated_at=recipe.updated_at,
    )


def _to_response(recipe: Recipe) -> RecipeResponse:
    """레시피 모델을 상세 응답 형식으로 변환합니다."""
    return RecipeResponse(
        **_to_summary(recipe).model_dump(by_alias=False),
        steps=recipe.steps,
        memo=recipe.memo,
    )


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


def _parse_recipe_part(recipe: str) -> RecipeCreateRequest:
    """multipart의 recipe JSON 파트를 검증합니다."""
    try:
        return RecipeCreateRequest.model_validate_json(recipe)
    except ValidationError as exc:
        raise RequestValidationError(
            exc.errors(include_url=False, include_context=False)
        ) from None


@router.post("", response_model=RecipeResponse, status_code=status.HTTP_201_CREATED)
async def create_recipe(
    store_id: UUID,
    recipe: Annotated[str, Form()],
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[RecipeService, Depends(get_recipe_service)],
    images: Annotated[list[UploadFile] | None, File()] = None,
) -> RecipeResponse:
    """매장의 레시피를 등록합니다."""
    # TODO: 파일 저장소가 정해지면 레시피 사진을 저장합니다.
    if images:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Recipe image upload is not supported yet",
        )
    request = _parse_recipe_part(recipe)
    with _translate_errors():
        created = await service.create(store_id, user.id, request)
    return _to_response(created)


@router.get("", response_model=RecipeListResponse)
async def list_recipes(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[RecipeService, Depends(get_recipe_service)],
) -> RecipeListResponse:
    """매장의 레시피 목록을 카테고리 정보와 함께 조회합니다."""
    with _translate_errors():
        recipes = await service.list_for_store(store_id, user.id)
    return RecipeListResponse(
        categories=[
            RecipeCategorySummary(name=name, count=count)
            for name, count in count_categories(recipes).items()
        ],
        default_category=None,
        recipes=[_to_summary(recipe) for recipe in recipes],
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
    return _to_response(recipe)


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
    return _to_response(recipe)


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
