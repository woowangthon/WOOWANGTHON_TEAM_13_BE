from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user
from app.core.config import settings
from app.db.session import get_db
from app.integrations.storage import SupabaseStorageClient
from app.models.user import User
from app.repositories.membership import MembershipRepository
from app.repositories.store import StoreRepository
from app.schemas.store_photo import StorePhotoResponse
from app.services.image import (
    MAX_IMAGE_BYTES,
    ImageStorageError,
    ImageTooLargeError,
    ImageTypeError,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError, StoreAccessService
from app.services.store_photo import StorePhotoService

router = APIRouter(prefix="/stores/{store_id}/photo", tags=["store-photos"])


def get_store_photo_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> StorePhotoService:
    """요청에 사용할 매장 사진 서비스를 생성합니다."""
    return StorePhotoService(
        StoreAccessService(StoreRepository(session), MembershipRepository(session)),
        SupabaseStorageClient(
            supabase_url=settings.supabase_url,
            secret_key=settings.supabase_secret_key,
            bucket=settings.supabase_store_photo_bucket,
        ),
    )


def _error_response(status_code: int, code: str, message: str) -> JSONResponse:
    """FE와 맞춘 code, message 형식의 오류 응답을 만듭니다."""
    return JSONResponse(
        status_code=status_code,
        content={"code": code, "message": message, "detail": None},
    )


@router.post(
    "",
    response_model=StorePhotoResponse,
    status_code=status.HTTP_201_CREATED,
    responses={
        status.HTTP_413_CONTENT_TOO_LARGE: {"description": "IMAGE_TOO_LARGE"},
        status.HTTP_415_UNSUPPORTED_MEDIA_TYPE: {
            "description": "UNSUPPORTED_IMAGE_TYPE"
        },
        status.HTTP_503_SERVICE_UNAVAILABLE: {"description": "STORAGE_UNAVAILABLE"},
    },
)
async def upload_store_photo(
    store_id: UUID,
    image: Annotated[UploadFile, File()],
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[StorePhotoService, Depends(get_store_photo_service)],
) -> StorePhotoResponse | JSONResponse:
    """매장 사진을 올리고 매장 수정 API의 photoUrl에 넣을 공개 주소를 돌려줍니다."""
    data = await image.read(MAX_IMAGE_BYTES + 1)
    try:
        url = await service.upload(store_id, user.id, data)
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
    except ImageTooLargeError:
        return _error_response(
            status.HTTP_413_CONTENT_TOO_LARGE,
            "IMAGE_TOO_LARGE",
            "10MB 이하 사진만 올릴 수 있어요",
        )
    except ImageTypeError:
        return _error_response(
            status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            "UNSUPPORTED_IMAGE_TYPE",
            "JPEG, PNG, WebP 사진만 올릴 수 있어요",
        )
    except ImageStorageError:
        return _error_response(
            status.HTTP_503_SERVICE_UNAVAILABLE,
            "STORAGE_UNAVAILABLE",
            "사진을 저장하지 못했어요. 잠시 후 다시 시도해 주세요",
        )
    return StorePhotoResponse(photo_url=url)
