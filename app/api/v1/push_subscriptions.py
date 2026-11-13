from typing import Annotated

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_active_user
from app.core.config import settings
from app.db.session import get_db
from app.models.user import User
from app.repositories.push_subscription import PushSubscriptionRepository
from app.schemas.push_subscription import (
    PushSubscriptionCreateRequest,
    PushSubscriptionDeleteRequest,
    PushSubscriptionResponse,
)
from app.services.push import PushService, build_push_sender

router = APIRouter(
    prefix="/users/me/push-subscriptions",
    tags=["push-subscriptions"],
)


def get_push_service(
    session: Annotated[AsyncSession, Depends(get_db)],
) -> PushService:
    return PushService(
        PushSubscriptionRepository(session),
        build_push_sender(settings.vapid_private_key, settings.vapid_subject),
    )


@router.post(
    "",
    response_model=PushSubscriptionResponse,
    status_code=status.HTTP_201_CREATED,
)
async def subscribe_to_push(
    request: PushSubscriptionCreateRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[PushService, Depends(get_push_service)],
) -> PushSubscriptionResponse:
    subscription = await service.subscribe(
        user.id,
        request.endpoint,
        request.keys.p256dh,
        request.keys.auth,
    )
    return PushSubscriptionResponse(subscription_id=subscription.id)


@router.delete("", status_code=status.HTTP_204_NO_CONTENT)
async def unsubscribe_from_push(
    request: PushSubscriptionDeleteRequest,
    user: Annotated[User, Depends(get_active_user)],
    service: Annotated[PushService, Depends(get_push_service)],
) -> Response:
    await service.unsubscribe(user.id, request.endpoint)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
