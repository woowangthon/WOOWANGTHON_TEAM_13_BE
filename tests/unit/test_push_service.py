from collections.abc import Sequence
from uuid import UUID, uuid4

from app.integrations.web_push import PushMessage, PushSubscriptionExpiredError
from app.models.push_subscription import PushSubscription
from app.services.push import PushService


class FakeRepository:
    def __init__(self) -> None:
        self.owner_id = uuid4()
        self.subscriptions = [
            PushSubscription(
                id=uuid4(),
                user_id=self.owner_id,
                endpoint="https://push.example/one",
                p256dh="p256dh",
                auth="auth",
            )
        ]
        self.deleted: list[UUID] = []

    async def upsert(
        self,
        user_id: UUID,
        endpoint: str,
        p256dh: str,
        auth: str,
    ) -> PushSubscription:
        return self.subscriptions[0]

    async def delete_for_user(self, user_id: UUID, endpoint: str) -> None:
        return None

    async def list_by_user_id(self, user_id: UUID) -> list[PushSubscription]:
        return self.subscriptions

    async def get_store_owner_id(self, store_id: UUID) -> UUID | None:
        return self.owner_id

    async def delete_by_ids(self, subscription_ids: Sequence[UUID]) -> None:
        self.deleted.extend(subscription_ids)


class FakeSender:
    def __init__(self, *, expired: bool = False, enabled: bool = True) -> None:
        self.enabled = enabled
        self.expired = expired
        self.messages: list[PushMessage] = []

    async def send(
        self,
        endpoint: str,
        p256dh: str,
        auth: str,
        message: PushMessage,
    ) -> None:
        self.messages.append(message)
        if self.expired:
            raise PushSubscriptionExpiredError


async def test_question_push_targets_store_owner() -> None:
    repository = FakeRepository()
    sender = FakeSender()
    service = PushService(repository, sender)
    store_id = uuid4()
    question_id = uuid4()

    await service.notify_owner_question(store_id, question_id, "우산을 빌려줘도 돼요?")

    assert len(sender.messages) == 1
    message = sender.messages[0]
    assert message.title == "새 질문이 도착했어요"
    assert message.url == f"/owner?store={store_id}&question={question_id}"


async def test_answer_push_targets_staff_chat() -> None:
    repository = FakeRepository()
    sender = FakeSender()
    service = PushService(repository, sender)
    store_id = uuid4()
    chat_id = uuid4()

    await service.notify_owner_answer(
        repository.owner_id,
        store_id,
        chat_id,
        "카운터 아래 우산을 빌려드려도 돼요.",
    )

    assert sender.messages[0].url == f"/staff/chat?store={store_id}&focus=owner-answer"


async def test_expired_subscription_is_deleted() -> None:
    repository = FakeRepository()
    sender = FakeSender(expired=True)
    service = PushService(repository, sender)

    await service.notify_owner_answer(
        repository.owner_id,
        uuid4(),
        uuid4(),
        "답변",
    )

    assert repository.deleted == [repository.subscriptions[0].id]


async def test_push_is_skipped_without_vapid_configuration() -> None:
    repository = FakeRepository()
    sender = FakeSender(enabled=False)
    service = PushService(repository, sender)

    await service.notify_owner_answer(
        repository.owner_id,
        uuid4(),
        uuid4(),
        "답변",
    )

    assert sender.messages == []
