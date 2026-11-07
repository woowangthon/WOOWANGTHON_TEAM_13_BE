from collections.abc import Iterator
from contextlib import contextmanager
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user, get_llm_client
from app.db.session import get_db
from app.integrations.llm import LLMClient, LLMError
from app.models.user import User
from app.repositories.store import StoreRepository
from app.schemas.recipe import RecipeScanResponse
from app.services.recipe_scan import (
    MAX_IMAGE_BYTES,
    RecipeImageSizeError,
    RecipeImageTypeError,
    RecipeImageUnreadableError,
    RecipeScanService,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessService

router = APIRouter(prefix="/stores/{store_id}/recipe-scans", tags=["recipes"])


def get_recipe_scan_service(
    session: Annotated[AsyncSession, Depends(get_db)],
    llm: Annotated[LLMClient, Depends(get_llm_client)],
) -> RecipeScanService:
    """요청에 사용할 레시피 스캔 서비스를 생성합니다."""
    return RecipeScanService(StoreAccessService(StoreRepository(session)), llm)


@contextmanager
def _translate_errors() -> Iterator[None]:
    """레시피 스캔 도메인 예외를 HTTP 오류로 변환합니다."""
    try:
        yield
    except StoreNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        ) from None
    except RecipeImageTypeError:
        raise HTTPException(
            status_code=415,
            detail="Unsupported image type",
        ) from None
    except RecipeImageSizeError:
        raise HTTPException(
            status_code=413,
            detail="Image must be between 1 byte and 10 MB",
        ) from None
    except RecipeImageUnreadableError:
        raise HTTPException(
            status_code=422,
            detail="Recipe could not be read from the image",
        ) from None
    except LLMError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="AI service is unavailable",
        ) from None


@router.post("", response_model=RecipeScanResponse)
async def scan_recipe(
    store_id: UUID,
    image: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[RecipeScanService, Depends(get_recipe_scan_service)],
) -> RecipeScanResponse:
    """사진을 저장하지 않고 AI 레시피 초안으로 변환합니다."""
    content = await image.read(MAX_IMAGE_BYTES + 1)
    with _translate_errors():
        draft = await service.scan(store_id, user.id, image.content_type, content)
    return RecipeScanResponse.model_validate(draft)
