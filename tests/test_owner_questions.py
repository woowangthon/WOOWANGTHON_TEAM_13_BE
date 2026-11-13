from datetime import UTC, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.assistant_chats import get_owner_question_service
from app.api.v1.owner_questions import router
from app.api.v1.push_subscriptions import get_push_service
from app.api.v1.users import get_user_service
from app.app import app
from app.core.auth import AuthenticatedUser, get_current_user
from app.integrations.llm import LLMError
from app.models.owner_question import OwnerQuestion
from app.models.user import User
from app.services.manual import ManualCategoryNotFoundError
from app.services.owner_question import (
    ManualDraft,
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
        self.seen_answer: tuple[str, ManualDraft | None] | None = None
        self.manual_id: UUID | None = None
        self.seen_draft_answer: str | None = None

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
        manual_draft: ManualDraft | None = None,
    ) -> OwnerQuestionView:
        if self.error is not None:
            raise self.error
        self.seen_answer = (text, manual_draft)
        self.question.status = "answered"
        self.question.answer = text
        self.question.answered_at = datetime.now(UTC)
        if manual_draft is not None:
            self.manual_id = uuid4()
        return OwnerQuestionView(self.question, "지은", self.manual_id)

    async def manual_draft(
        self,
        store_id: UUID,
        question_id: UUID,
        user_id: UUID,
        answer: str,
    ) -> ManualDraft:
        if self.error is not None:
            raise self.error
        self.seen_draft_answer = answer
        return ManualDraft(title="우산 대여", body="카운터 아래 우산을 빌려드려요.")


class StubPushService:
    def __init__(self) -> None:
        self.answer: tuple[UUID, UUID, UUID, str] | None = None

    async def notify_owner_answer(
        self,
        staff_id: UUID,
        store_id: UUID,
        chat_id: UUID,
        answer: str,
    ) -> None:
        self.answer = (staff_id, store_id, chat_id, answer)


PUSH = StubPushService()


def make_client() -> tuple[TestClient, StubOwnerQuestionService]:
    service = StubOwnerQuestionService()
    PUSH.answer = None
    test_app = FastAPI()
    test_app.include_router(router)

    def authenticated_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=uuid4(), email=None, role=None, claims={})

    test_app.dependency_overrides[get_current_user] = authenticated_user
    test_app.dependency_overrides[get_user_service] = StubUserService
    test_app.dependency_overrides[get_owner_question_service] = lambda: service
    test_app.dependency_overrides[get_push_service] = lambda: PUSH
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
    assert response.json()["manualId"] is None
    assert service.seen_answer == ("카운터 아래 우산 빌려주세요", None)
    assert PUSH.answer == (
        service.question.asked_by,
        STORE_ID,
        service.question.chat_id,
        "카운터 아래 우산 빌려주세요",
    )


def test_answer_and_add_to_manual() -> None:
    client, service = make_client()
    category_id = uuid4()

    response = client.post(
        questions_url(f"/{service.question.id}/answer"),
        json={
            "answer": "창고 왼쪽 선반",
            "addToManual": True,
            "manualTitle": " 청소도구 위치 ",
            "manualBody": "창고 왼쪽 선반에 빗자루, 쓰레받기",
            "manualCategoryId": str(category_id),
        },
    )

    assert response.status_code == 200
    assert response.json()["manualId"] == str(service.manual_id)
    assert service.seen_answer == (
        "창고 왼쪽 선반",
        ManualDraft(
            title="청소도구 위치",
            body="창고 왼쪽 선반에 빗자루, 쓰레받기",
            category_id=category_id,
        ),
    )


def test_add_to_manual_blank_edits_use_defaults() -> None:
    client, service = make_client()

    response = client.post(
        questions_url(f"/{service.question.id}/answer"),
        json={
            "answer": "답",
            "addToManual": True,
            "manualTitle": "  ",
            "manualBody": "",
        },
    )

    assert response.status_code == 200
    assert service.seen_answer == ("답", ManualDraft())


def test_manual_fields_ignored_without_add_to_manual() -> None:
    client, service = make_client()

    response = client.post(
        questions_url(f"/{service.question.id}/answer"),
        json={"answer": "답", "manualTitle": "제목"},
    )

    assert response.status_code == 200
    assert service.seen_answer == ("답", None)


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

    service.error = ManualCategoryNotFoundError()
    bad_category = client.post(url, json=body)
    service.error = OwnerQuestionAlreadyAnsweredError()
    answered = client.post(url, json=body)
    service.error = OwnerQuestionNotFoundError()
    missing = client.post(url, json=body)
    service.error = StoreAccessForbiddenError()
    forbidden = client.post(url, json=body)

    assert bad_category.status_code == 422
    assert answered.status_code == 409
    assert answered.json()["code"] == "OWNER_QUESTION_ALREADY_ANSWERED"
    assert missing.status_code == 404
    assert forbidden.status_code == 403


def test_manual_draft_route_is_registered() -> None:
    paths = app.openapi()["paths"]

    assert (
        "/api/v1/stores/{store_id}/owner-questions/{question_id}/manual-draft" in paths
    )


def test_manual_draft_returns_title_and_body() -> None:
    client, service = make_client()

    response = client.post(
        questions_url(f"/{service.question.id}/manual-draft"),
        json={"answer": " 카운터 아래 우산 빌려줘 "},
    )

    assert response.status_code == 200
    assert response.json() == {
        "title": "우산 대여",
        "body": "카운터 아래 우산을 빌려드려요.",
    }
    assert service.seen_draft_answer == "카운터 아래 우산 빌려줘"
    assert service.question.status == "asked"


def test_manual_draft_errors() -> None:
    client, service = make_client()
    url = questions_url(f"/{service.question.id}/manual-draft")

    blank = client.post(url, json={"answer": "  "})
    service.error = LLMError("timeout")
    unavailable = client.post(url, json={"answer": "답"})
    service.error = StoreAccessForbiddenError()
    forbidden = client.post(url, json={"answer": "답"})
    service.error = OwnerQuestionNotFoundError()
    missing = client.post(url, json={"answer": "답"})

    assert blank.status_code == 422
    assert unavailable.status_code == 503
    assert unavailable.json()["code"] == "AI_UNAVAILABLE"
    assert forbidden.status_code == 403
    assert missing.status_code == 404
