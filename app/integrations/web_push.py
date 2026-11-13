import asyncio
import json
from dataclasses import dataclass

from pywebpush import WebPushException, webpush  # type: ignore[import-untyped]


class PushSubscriptionExpiredError(Exception):
    """브라우저 푸시 서비스에서 더 이상 존재하지 않는 구독이라고 응답했습니다."""


class PushDeliveryError(Exception):
    """일시적 또는 알 수 없는 이유로 푸시 발송에 실패했습니다."""


@dataclass(frozen=True)
class PushMessage:
    title: str
    body: str
    url: str
    tag: str


class WebPushSender:
    def __init__(self, private_key: str, subject: str) -> None:
        self._private_key = private_key.strip()
        self._subject = subject.strip()

    @property
    def enabled(self) -> bool:
        return bool(self._private_key and self._subject)

    async def send(
        self,
        endpoint: str,
        p256dh: str,
        auth: str,
        message: PushMessage,
    ) -> None:
        if not self.enabled:
            return
        payload = json.dumps(
            {
                "title": message.title,
                "body": message.body,
                "url": message.url,
                "tag": message.tag,
            },
            ensure_ascii=False,
        )
        try:
            await asyncio.to_thread(
                webpush,
                subscription_info={
                    "endpoint": endpoint,
                    "keys": {"p256dh": p256dh, "auth": auth},
                },
                data=payload,
                vapid_private_key=self._private_key,
                vapid_claims={"sub": self._subject},
                timeout=5,
                ttl=60 * 60 * 24,
            )
        except WebPushException as exc:
            status_code = exc.response.status_code if exc.response is not None else None
            if status_code in (404, 410):
                raise PushSubscriptionExpiredError from exc
            raise PushDeliveryError from exc
