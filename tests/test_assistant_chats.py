from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.assistant_chats import get_assistant_chat_service, router
from app.api.v1.users import get_user_service
from app.app import app
from app.core.auth import AuthenticatedUser, get_current_user
from app.integrations.llm import LLMError
from app.models.assistant_chat import AssistantChat, AssistantMessage
from app.models.user import User
from app.services.assistant_chat import (
    AssistantChatNotFoundError,
    AssistantMessageNotFoundError,
)
from app.services.store import StoreNotFoundError

STORE_ID = uuid4()
SOURCE_ID = uuid4()


class StubUserService:
    async def get_or_create(self, identity: AuthenticatedUser) -> User:
        return User(
            id=uuid4(),
            auth_user_id=uuid4(),
            nickname="홍길동",
            email=None,
            provider="kakao",
        )


def make_message(sender: str, text: str, answer_type: str | None) -> AssistantMessage:
    sources = []
    if answer_type == "answered":
        sources = [{"kind": "recipe", "id": str(SOURCE_ID), "title": "딸기라떼"}]
    return AssistantMessage(
        id=uuid4(),
        chat_id=uuid4(),
        sender=sender,
        text=text,
        answer_type=answer_type,
        sources=sources,
        created_at=datetime.now(UTC),
    )


class StubChatService:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.chat = AssistantChat(
            id=uuid4(),
            store_id=STORE_ID,
            user_id=uuid4(),
            last_message_at=now,
            last_message_text=None,
            created_at=now,
        )
        self.error: Exception | None = None
        self.deleted = False
        self.seen_limit = 0
        self.seen_before: UUID | None = None

    def _raise_if_needed(self) -> None:
        if self.error is not None:
            raise self.error

    async def create_chat(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> tuple[AssistantChat, list[str]]:
        self._raise_if_needed()
        return self.chat, ["와이파이"]

    async def list_chats(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> tuple[list[AssistantChat], list[str]]:
        self._raise_if_needed()
        return [self.chat], ["와이파이"]

    async def delete_chat(
        self,
        store_id: UUID,
        chat_id: UUID,
        user_id: UUID,
    ) -> None:
        self._raise_if_needed()
        self.deleted = True

    async def send_message(
        self,
        store_id: UUID,
        chat_id: UUID,
        user_id: UUID,
        text: str,
    ) -> tuple[AssistantMessage, AssistantMessage]:
        self._raise_if_needed()
        return (
            make_message("staff", text, None),
            make_message("ai", "3스푼이에요", "answered"),
        )

    async def list_messages(
        self,
        store_id: UUID,
        chat_id: UUID,
        user_id: UUID,
        before_id: UUID | None,
        limit: int,
    ) -> tuple[list[AssistantMessage], bool]:
        self._raise_if_needed()
        self.seen_limit = limit
        self.seen_before = before_id
        return [make_message("staff", "질문", None)], True


def make_client() -> tuple[TestClient, StubChatService]:
    service = StubChatService()
    test_app = FastAPI()
    test_app.include_router(router)

    def authenticated_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=uuid4(), email=None, role=None, claims={})

    test_app.dependency_overrides[get_current_user] = authenticated_user
    test_app.dependency_overrides[get_user_service] = StubUserService
    test_app.dependency_overrides[get_assistant_chat_service] = lambda: service
    return TestClient(test_app), service


def chats_url(suffix: str = "") -> str:
    return f"/stores/{STORE_ID}/assistant-chats{suffix}"


def test_assistant_routes_are_registered_in_application() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores/{store_id}/assistant-chats" in paths
    assert "/api/v1/stores/{store_id}/assistant-chats/{chat_id}" in paths
    assert "/api/v1/stores/{store_id}/assistant-chats/{chat_id}/messages" in paths


def test_create_chat_without_body() -> None:
    client, _ = make_client()

    response = client.post(chats_url())

    assert response.status_code == 201
    assert set(response.json()) == {
        "chatId",
        "storeId",
        "createdAt",
        "lastMessageAt",
        "lastMessageText",
        "suggestions",
        "messages",
    }


def test_list_chats_returns_suggestions_and_chats() -> None:
    client, service = make_client()

    response = client.get(chats_url())

    assert response.status_code == 200
    assert response.json()["suggestions"] == ["와이파이"]
    assert response.json()["chats"][0]["chatId"] == str(service.chat.id)


def test_send_message_returns_question_and_answer() -> None:
    client, service = make_client()

    response = client.post(
        chats_url(f"/{service.chat.id}/messages"),
        json={"text": " 딸기청 몇 스푼? "},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["question"]["text"] == "딸기청 몇 스푼?"
    assert body["question"]["answerType"] is None
    assert body["answer"]["answerType"] == "answered"
    assert body["answer"]["sources"] == [
        {"kind": "recipe", "id": str(SOURCE_ID), "title": "딸기라떼"}
    ]
    assert body["answer"]["canAskOwner"] is False
    assert body["answer"]["ownerQuestion"] is None


def test_send_message_rejects_blank_and_too_long_text() -> None:
    client, service = make_client()
    url = chats_url(f"/{service.chat.id}/messages")

    assert client.post(url, json={"text": "  "}).status_code == 422
    assert client.post(url, json={"text": "가" * 1001}).status_code == 422


def test_llm_failure_returns_503() -> None:
    client, service = make_client()
    service.error = LLMError()

    response = client.post(
        chats_url(f"/{service.chat.id}/messages"),
        json={"text": "질문"},
    )

    assert response.status_code == 503


def test_list_messages_passes_cursor_and_limit() -> None:
    client, service = make_client()
    before = uuid4()

    response = client.get(
        chats_url(f"/{service.chat.id}/messages"),
        params={"before": str(before), "limit": 10},
    )

    assert response.status_code == 200
    assert response.json()["hasMore"] is True
    assert response.json()["chatId"] == str(service.chat.id)
    assert service.seen_before == before
    assert service.seen_limit == 10


def test_list_messages_rejects_invalid_limit() -> None:
    client, service = make_client()
    url = chats_url(f"/{service.chat.id}/messages")

    assert client.get(url, params={"limit": 0}).status_code == 422
    assert client.get(url, params={"limit": 101}).status_code == 422


def test_not_found_errors_return_404() -> None:
    client, service = make_client()
    url = chats_url(f"/{service.chat.id}/messages")

    for error in (
        StoreNotFoundError(),
        AssistantChatNotFoundError(),
        AssistantMessageNotFoundError(),
    ):
        service.error = error
        assert client.get(url).status_code == 404


def test_delete_chat() -> None:
    client, service = make_client()

    response = client.delete(chats_url(f"/{service.chat.id}"))

    assert response.status_code == 204
    assert service.deleted is True
