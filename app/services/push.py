import asyncio
import logging
from collections.abc import Sequence
from typing import Protocol
from uuid import UUID

from app.integrations.web_push import (
    PushDeliveryError,
    PushMessage,
    PushSubscriptionExpiredError,
    WebPushSender,
)
from app.models.push_subscription import PushSubscription

logger = logging.getLogger(__name__)


class PushSubscriptionRepositoryProtocol(Protocol):
    async def upsert(
        self,
        user_id: UUID,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> PushSubscription: ...

    async def delete_for_user(self, user_id: UUID, endpoint: str) -> None: ...

    async def list_by_user_id(self, user_id: UUID) -> list[PushSubscription]: ...

    async def get_store_owner_id(self, store_id: UUID) -> UUID | None: ...

    async def delete_by_ids(self, subscription_ids: Sequence[UUID]) -> None: ...


class PushSenderProtocol(Protocol):
    @property
    def enabled(self) -> bool: ...

    async def send(
        self,
        endpoint: str,
        p256dh: str,
        auth: str,
        message: PushMessage,
    ) -> None: ...


class PushService:
    def __init__(
        self,
        repository: PushSubscriptionRepositoryProtocol,
        sender: PushSenderProtocol,
    ) -> None:
        self._repository = repository
        self._sender = sender

    async def subscribe(
        self,
        user_id: UUID,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> PushSubscription:
        return await self._repository.upsert(user_id, endpoint, p256dh, auth)

    async def unsubscribe(self, user_id: UUID, endpoint: str) -> None:
        await self._repository.delete_for_user(user_id, endpoint)

    async def notify_owner_question(
        self,
        store_id: UUID,
        question_id: UUID,
        question: str,
    ) -> None:
        owner_id = await self._repository.get_store_owner_id(store_id)
        if owner_id is None:
            return
        await self._notify(
            owner_id,
            PushMessage(
                title="새 질문이 도착했어요",
                body=_preview(question),
                url=f"/owner?store={store_id}&question={question_id}",
                tag=f"owner-question-{question_id}",
            ),
        )

    async def notify_owner_answer(
        self,
        staff_id: UUID,
        store_id: UUID,
        chat_id: UUID,
        answer: str,
    ) -> None:
        await self._notify(
            staff_id,
            PushMessage(
                title="사장님이 답변했어요",
                body=_preview(answer),
                url=f"/staff/chat?store={store_id}&focus=owner-answer",
                tag=f"owner-answer-{chat_id}",
            ),
        )

    async def _notify(self, user_id: UUID, message: PushMessage) -> None:
        if not self._sender.enabled:
            return
        subscriptions = await self._repository.list_by_user_id(user_id)
        results = await asyncio.gather(
            *(
                self._sender.send(
                    subscription.endpoint,
                    subscription.p256dh,
                    subscription.auth,
                    message,
                )
                for subscription in subscriptions
            ),
            return_exceptions=True,
        )
        expired: list[UUID] = []
        for subscription, result in zip(subscriptions, results, strict=True):
            if isinstance(result, PushSubscriptionExpiredError):
                expired.append(subscription.id)
            elif isinstance(result, PushDeliveryError):
                logger.warning("Web Push delivery failed", exc_info=result)
            elif isinstance(result, BaseException):
                logger.exception("Unexpected Web Push error", exc_info=result)
        await self._repository.delete_by_ids(expired)


def build_push_sender(private_key: str, subject: str) -> WebPushSender:
    return WebPushSender(private_key, subject)


def _preview(text: str, limit: int = 120) -> str:
    normalized = " ".join(text.split())
    if len(normalized) <= limit:
        return normalized
    return normalized[: limit - 1].rstrip() + "…"
