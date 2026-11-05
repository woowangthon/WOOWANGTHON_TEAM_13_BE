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
from app.models.manual import Manual
from app.models.user import User
from app.repositories.manual import ManualRepository
from app.repositories.store import StoreRepository
from app.schemas.manual import (
    ManualCategoryCreateRequest,
    ManualCategoryResponse,
    ManualCreateRequest,
    ManualListResponse,
    ManualRecommendation,
    ManualRecommendationListResponse,
    ManualRecommendationRequest,
    ManualResponse,
    ManualUpdateRequest,
)
from app.services.manual import (
    ManualCategoryNotFoundError,
    ManualNotFoundError,
    ManualService,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessService

router = APIRouter(prefix="/stores/{store_id}", tags=["manuals"])

NEW_BADGE_PERIOD = timedelta(days=3)


def get_manual_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> ManualService:
    """요청에 사용할 매뉴얼 서비스를 생성합니다."""
    return ManualService(
        ManualRepository(session),
        StoreAccessService(StoreRepository(session)),
    )


def _to_response(manual: Manual) -> ManualResponse:
    """매뉴얼 모델을 API 응답 형식으로 변환합니다."""
    return ManualResponse(
        manual_id=manual.id,
        category_id=manual.category_id,
        icon=manual.icon,
        title=manual.title,
        body=manual.body,
        is_new=datetime.now(UTC) - manual.updated_at <= NEW_BADGE_PERIOD,
        updated_at=manual.updated_at,
    )


@contextmanager
def _translate_errors() -> Iterator[None]:
    """매뉴얼 도메인 예외를 HTTP 오류로 변환합니다."""
    try:
        yield
    except StoreNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        ) from None
    except ManualNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Manual not found",
        ) from None
    except ManualCategoryNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="Manual category not found",
        ) from None


def _parse_manual_part(manual: str) -> ManualCreateRequest:
    """multipart의 manual JSON 파트를 검증합니다."""
    try:
        return ManualCreateRequest.model_validate_json(manual)
    except ValidationError as exc:
        raise RequestValidationError(
            exc.errors(include_url=False, include_context=False)
        ) from None


@router.post(
    "/manual-categories",
    response_model=ManualCategoryResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual_category(
    store_id: UUID,
    request: ManualCategoryCreateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ManualService, Depends(get_manual_service)],
) -> ManualCategoryResponse:
    """매장의 매뉴얼 카테고리를 생성합니다."""
    with _translate_errors():
        category = await service.create_category(store_id, user.id, request)
    return ManualCategoryResponse(category_id=category.id, name=category.name)


@router.post(
    "/manuals/recommendations",
    response_model=ManualRecommendationListResponse,
)
async def recommend_manuals(
    store_id: UUID,
    request: ManualRecommendationRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ManualService, Depends(get_manual_service)],
) -> ManualRecommendationListResponse:
    """등록할 만한 매뉴얼 템플릿을 추천합니다."""
    with _translate_errors():
        templates = await service.recommend(store_id, user.id, request.keywords)
    return ManualRecommendationListResponse(
        recommendations=[
            ManualRecommendation(
                icon=template.icon,
                title=template.title,
                body=template.body,
            )
            for template in templates
        ]
    )


@router.post(
    "/manuals",
    response_model=ManualResponse,
    status_code=status.HTTP_201_CREATED,
)
async def create_manual(
    store_id: UUID,
    manual: Annotated[str, Form()],
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ManualService, Depends(get_manual_service)],
    files: Annotated[list[UploadFile] | None, File()] = None,
) -> ManualResponse:
    """매장의 매뉴얼을 등록합니다."""
    # TODO: 파일 저장소가 정해지면 첨부파일을 저장합니다.
    if files:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail="Manual file upload is not supported yet",
        )
    request = _parse_manual_part(manual)
    with _translate_errors():
        created = await service.create(store_id, user.id, request)
    return _to_response(created)


@router.get("/manuals", response_model=ManualListResponse)
async def list_manuals(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ManualService, Depends(get_manual_service)],
) -> ManualListResponse:
    """매장의 매뉴얼 목록을 조회합니다."""
    with _translate_errors():
        manuals = await service.list_for_store(store_id, user.id)
    return ManualListResponse(manuals=[_to_response(item) for item in manuals])


@router.get("/manuals/{manual_id}", response_model=ManualResponse)
async def get_manual(
    store_id: UUID,
    manual_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ManualService, Depends(get_manual_service)],
) -> ManualResponse:
    """매장의 매뉴얼 상세 정보를 조회합니다."""
    with _translate_errors():
        manual = await service.get(store_id, manual_id, user.id)
    return _to_response(manual)


@router.patch("/manuals/{manual_id}", response_model=ManualResponse)
async def update_manual(
    store_id: UUID,
    manual_id: UUID,
    request: ManualUpdateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ManualService, Depends(get_manual_service)],
) -> ManualResponse:
    """매장의 매뉴얼을 수정합니다."""
    with _translate_errors():
        manual = await service.update(store_id, manual_id, user.id, request)
    return _to_response(manual)


@router.delete("/manuals/{manual_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_manual(
    store_id: UUID,
    manual_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[ManualService, Depends(get_manual_service)],
) -> Response:
    """매장의 매뉴얼을 삭제 처리합니다."""
    with _translate_errors():
        await service.delete(store_id, manual_id, user.id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
