from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user
from app.db.session import get_db
from app.models.user import User
from app.repositories.notification import NotificationRepository
from app.repositories.payroll import PayrollRepository
from app.schemas.notification import (
    NotificationItem,
    NotificationListResponse,
    NotificationTarget,
    ShiftBannerItem,
    ShiftBannerResponse,
)
from app.services.notification import (
    NotificationFeed,
    NotificationService,
    ShiftBanner,
    is_read,
)
from app.services.store import StoreNotFoundError

router = APIRouter(
    prefix="/stores/{store_id}/notifications",
    tags=["notifications"],
)


def get_notification_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> NotificationService:
    """요청에 사용할 알림 서비스를 생성합니다."""
    return NotificationService(
        NotificationRepository(session),
        PayrollRepository(session),
    )


def _to_banner(banner: ShiftBanner) -> ShiftBannerResponse:
    """출근 전 배너를 응답 형식으로 변환합니다."""
    return ShiftBannerResponse(
        work_date=banner.work_date,
        start_time=banner.start_time.strftime("%H:%M"),
        end_time=banner.end_time.strftime("%H:%M"),
        starts_at=banner.starts_at,
        unchecked_count=len(banner.items),
        items=[
            ShiftBannerItem(
                note_id=item.note_id,
                item_id=item.item_id,
                tag=item.tag,
                text=item.text,
                author_name=item.author_name,
                work_date=item.work_date,
            )
            for item in banner.items
        ],
    )


def _to_response(feed: NotificationFeed) -> NotificationListResponse:
    """알림 묶음을 응답 형식으로 변환합니다."""
    return NotificationListResponse(
        banner=_to_banner(feed.banner) if feed.banner is not None else None,
        notifications=[
            NotificationItem(
                notification_id=item.notification_id,
                type=item.type,
                title=item.title,
                body=item.body,
                created_at=item.created_at,
                is_read=is_read(item, feed.last_read_at),
                target=NotificationTarget(
                    kind=item.target_kind, id=item.target_id, work_date=item.work_date
                ),
            )
            for item in feed.notifications
        ],
        unread_count=feed.unread_count,
    )


@router.get("", response_model=NotificationListResponse)
async def list_notifications(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> NotificationListResponse:
    """내 역할에 맞는 최근 14일 알림과 출근 전 인수인계 배너를 조회합니다."""
    try:
        feed = await service.feed(store_id, user.id)
    except StoreNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        ) from None
    return _to_response(feed)


@router.post("/read", status_code=status.HTTP_204_NO_CONTENT)
async def read_notifications(
    store_id: UUID,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[NotificationService, Depends(get_notification_service)],
) -> Response:
    """지금까지의 알림을 모두 읽음으로 표시합니다."""
    try:
        await service.mark_all_read(store_id, user.id)
    except StoreNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Store not found",
        ) from None
    return Response(status_code=status.HTTP_204_NO_CONTENT)
