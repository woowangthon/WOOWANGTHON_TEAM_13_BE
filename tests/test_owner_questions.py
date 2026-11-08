from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.assistant_chats import get_owner_question_service
from app.api.v1.owner_questions import router
from app.api.v1.users import get_user_service
from app.app import app
from app.core.auth import AuthenticatedUser, get_current_user
from app.models.owner_question import OwnerQuestion
from app.models.user import User
from app.services.owner_question import (
    AddToManualNotSupportedError,
    OwnerQuestionAlreadyAnsweredError,
    OwnerQuestionNotFoundError,
    OwnerQuestionView,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError

STORE_ID = uuid4()


class StubUserService:
    async def get_or_create(self, identity: AuthenticatedUser) -> User:
        return User(
            id=uuid4(),
            auth_user_id=uuid4(),
            nickname="사장님",
            email=None,
            provider="kakao",
        )


def make_question(status: str = "asked") -> OwnerQuestion:
    return OwnerQuestion(
        id=uuid4(),
        store_id=STORE_ID,
        chat_id=uuid4(),
        message_id=uuid4(),
        asked_by=uuid4(),
        question="손님이 비 와서 우산 빌려 달래요. 카운터 아래 우산 빌려드려도 되나요?",
        status=status,
        answer=None,
        answered_at=None,
        created_at=datetime.now(UTC),
    )


class StubOwnerQuestionService:
    def __init__(self) -> None:
        self.error: Exception | None = None
        self.question = make_question()
        self.seen_status: str | None = "unset"
        self.seen_answer: tuple[str, bool] | None = None

    async def list_questions(
        self,
        store_id: UUID,
        user_id: UUID,
        status: str | None,
    ) -> list[OwnerQuestionView]:
        if self.error is not None:
            raise self.error
        self.seen_status = status
        return [OwnerQuestionView(self.question, "지은")]

    async def answer(
        self,
        store_id: UUID,
        question_id: UUID,
        user_id: UUID,
        text: str,
        add_to_manual: bool,
    ) -> OwnerQuestionView:
        if self.error is not None:
            raise self.error
        self.seen_answer = (text, add_to_manual)
        self.question.status = "answered"
        self.question.answer = text
        self.question.answered_at = datetime.now(UTC)
        return OwnerQuestionView(self.question, "지은")


def make_client() -> tuple[TestClient, StubOwnerQuestionService]:
    service = StubOwnerQuestionService()
    test_app = FastAPI()
    test_app.include_router(router)

    def authenticated_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=uuid4(), email=None, role=None, claims={})

    test_app.dependency_overrides[get_current_user] = authenticated_user
    test_app.dependency_overrides[get_user_service] = StubUserService
    test_app.dependency_overrides[get_owner_question_service] = lambda: service
    return TestClient(test_app), service


def questions_url(suffix: str = "") -> str:
    return f"/stores/{STORE_ID}/owner-questions{suffix}"


def test_owner_question_routes_are_registered() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores/{store_id}/owner-questions" in paths
    assert "/api/v1/stores/{store_id}/owner-questions/{question_id}/answer" in paths


def test_list_questions_returns_camel_case_items() -> None:
    client, service = make_client()

    response = client.get(questions_url(), params={"status": "asked"})

    assert response.status_code == 200
    item = response.json()["questions"][0]
    assert set(item) == {
        "questionId",
        "storeId",
        "title",
        "question",
        "icon",
        "staffName",
        "askedAt",
        "status",
        "answer",
        "answeredAt",
    }
    assert item["title"] == service.question.question[:30].rstrip() + "…"
    assert item["icon"] is None
    assert item["staffName"] == "지은"
    assert service.seen_status == "asked"


def test_list_questions_without_status_returns_all() -> None:
    client, service = make_client()

    assert client.get(questions_url()).status_code == 200
    assert service.seen_status is None


def test_list_questions_rejects_unknown_status() -> None:
    client, _ = make_client()

    assert client.get(questions_url(), params={"status": "done"}).status_code == 422


def test_staff_gets_403_and_stranger_gets_404() -> None:
    client, service = make_client()

    service.error = StoreAccessForbiddenError()
    forbidden = client.get(questions_url())
    service.error = StoreNotFoundError()
    missing = client.get(questions_url())

    assert forbidden.status_code == 403
    assert missing.status_code == 404


def test_answer_question() -> None:
    client, service = make_client()

    response = client.post(
        questions_url(f"/{service.question.id}/answer"),
        json={"answer": " 카운터 아래 우산 빌려주세요 ", "addToManual": False},
    )

    assert response.status_code == 200
    assert response.json()["status"] == "answered"
    assert response.json()["answer"] == "카운터 아래 우산 빌려주세요"
    assert service.seen_answer == ("카운터 아래 우산 빌려주세요", False)


def test_answer_rejects_blank_text() -> None:
    client, service = make_client()

    response = client.post(
        questions_url(f"/{service.question.id}/answer"),
        json={"answer": "  "},
    )

    assert response.status_code == 422


def test_answer_error_codes() -> None:
    client, service = make_client()
    url = questions_url(f"/{service.question.id}/answer")
    body = {"answer": "답변", "addToManual": True, "manualTitle": "우산 대여"}

    service.error = AddToManualNotSupportedError()
    not_supported = client.post(url, json=body)
    service.error = OwnerQuestionAlreadyAnsweredError()
    answered = client.post(url, json=body)
    service.error = OwnerQuestionNotFoundError()
    missing = client.post(url, json=body)
    service.error = StoreAccessForbiddenError()
    forbidden = client.post(url, json=body)

    assert not_supported.status_code == 501
    assert not_supported.json()["code"] == "ADD_TO_MANUAL_NOT_SUPPORTED"
    assert answered.status_code == 409
    assert answered.json()["code"] == "OWNER_QUESTION_ALREADY_ANSWERED"
    assert missing.status_code == 404
    assert forbidden.status_code == 403
