from datetime import UTC, date, datetime
from uuid import UUID, uuid4

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.v1.handovers import get_handover_service, router
from app.api.v1.users import get_user_service
from app.app import app
from app.core.auth import AuthenticatedUser, get_current_user
from app.integrations.llm import LLMError
from app.models.handover import HandoverItem, HandoverNote
from app.models.user import User
from app.schemas.handover import (
    HandoverConfirmationRequest,
    HandoverNoteCreateRequest,
    HandoverNoteUpdateRequest,
)
from app.services.handover import (
    HandoverDraft,
    HandoverForbiddenError,
    HandoverItemNotFoundError,
    HandoverNoteNotFoundError,
)
from app.services.store import StoreNotFoundError

STORE_ID = uuid4()
AUTHOR = User(
    id=uuid4(),
    auth_user_id=uuid4(),
    nickname="민수",
    email=None,
    provider="kakao",
)
CHECKER = User(
    id=uuid4(),
    auth_user_id=uuid4(),
    nickname="지은",
    email=None,
    provider="kakao",
)


class StubUserService:
    async def get_or_create(self, identity: AuthenticatedUser) -> User:
        return AUTHOR


class StubHandoverService:
    def __init__(self) -> None:
        now = datetime.now(UTC)
        self.item = HandoverItem(
            id=uuid4(),
            position=0,
            tag="stock",
            text="딸기청 1병 남음",
            checked=True,
            checked_at=now,
        )
        self.item.checked_by = CHECKER
        self.note = HandoverNote(
            id=uuid4(),
            store_id=STORE_ID,
            author_id=AUTHOR.id,
            work_date=date(2026, 11, 20),
            raw_text="딸기청 1병 남았어요",
            no_issue=False,
            summary="딸기청 1병 남음",
            created_at=now,
            updated_at=now,
        )
        self.note.author = AUTHOR
        self.note.items = [self.item]
        self.error: Exception | None = None
        self.seen_date: date | None = None
        self.deleted = False

    def _raise_if_needed(self) -> None:
        if self.error is not None:
            raise self.error

    async def create_draft(
        self,
        store_id: UUID,
        user_id: UUID,
        text: str,
    ) -> HandoverDraft:
        self._raise_if_needed()
        return HandoverDraft("요약", [{"tag": "etc", "text": text}])

    async def create(
        self,
        store_id: UUID,
        user_id: UUID,
        request: HandoverNoteCreateRequest,
    ) -> HandoverNote:
        self._raise_if_needed()
        return self.note

    async def list_by_date(
        self,
        store_id: UUID,
        user_id: UUID,
        work_date: date | None,
    ) -> tuple[date, list[HandoverNote]]:
        self._raise_if_needed()
        self.seen_date = work_date
        return work_date or date(2026, 11, 20), [self.note]

    async def get(
        self,
        store_id: UUID,
        note_id: UUID,
        user_id: UUID,
    ) -> HandoverNote:
        self._raise_if_needed()
        return self.note

    async def update(
        self,
        store_id: UUID,
        note_id: UUID,
        user_id: UUID,
        request: HandoverNoteUpdateRequest,
    ) -> HandoverNote:
        self._raise_if_needed()
        return self.note

    async def delete(self, store_id: UUID, note_id: UUID, user_id: UUID) -> None:
        self._raise_if_needed()
        self.deleted = True

    async def confirm(
        self,
        store_id: UUID,
        note_id: UUID,
        user_id: UUID,
        request: HandoverConfirmationRequest,
    ) -> HandoverNote:
        self._raise_if_needed()
        return self.note


def make_client() -> tuple[TestClient, StubHandoverService]:
    service = StubHandoverService()
    test_app = FastAPI()
    test_app.include_router(router)

    def authenticated_user() -> AuthenticatedUser:
        return AuthenticatedUser(id=uuid4(), email=None, role=None, claims={})

    test_app.dependency_overrides[get_current_user] = authenticated_user
    test_app.dependency_overrides[get_user_service] = StubUserService
    test_app.dependency_overrides[get_handover_service] = lambda: service
    return TestClient(test_app), service


def notes_url(suffix: str = "") -> str:
    return f"/stores/{STORE_ID}/handover-notes{suffix}"


def test_handover_routes_are_registered_in_application() -> None:
    paths = app.openapi()["paths"]

    assert "/api/v1/stores/{store_id}/handover-drafts" in paths
    assert "/api/v1/stores/{store_id}/handover-notes" in paths
    assert "/api/v1/stores/{store_id}/handover-notes/{note_id}" in paths
    assert "/api/v1/stores/{store_id}/handover-notes/{note_id}/confirmations" in paths


def test_create_draft() -> None:
    client, _ = make_client()

    response = client.post(
        f"/stores/{STORE_ID}/handover-drafts",
        json={"text": " 우유 부족 "},
    )

    assert response.status_code == 200
    assert response.json() == {
        "summary": "요약",
        "items": [{"tag": "etc", "text": "우유 부족"}],
    }


def test_create_draft_rejects_blank_text() -> None:
    client, _ = make_client()

    response = client.post(
        f"/stores/{STORE_ID}/handover-drafts",
        json={"text": "  "},
    )

    assert response.status_code == 422


def test_draft_failure_returns_503() -> None:
    client, service = make_client()
    service.error = LLMError()

    response = client.post(
        f"/stores/{STORE_ID}/handover-drafts",
        json={"text": "내용"},
    )

    assert response.status_code == 503


def test_create_note_returns_contract_shape() -> None:
    client, _ = make_client()

    response = client.post(
        notes_url(),
        json={
            "rawText": "원문",
            "noIssue": False,
            "summary": "요약",
            "items": [{"tag": "stock", "text": "내용"}],
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body) == {
        "noteId",
        "author",
        "createdAt",
        "updatedAt",
        "rawText",
        "noIssue",
        "summary",
        "items",
    }
    assert body["author"]["name"] == "민수"
    assert body["items"][0]["checkedBy"]["name"] == "지은"
    assert set(body["items"][0]) == {
        "itemId",
        "tag",
        "text",
        "checked",
        "checkedBy",
        "checkedAt",
    }


def test_create_note_rejects_invalid_values() -> None:
    client, _ = make_client()

    assert client.post(notes_url(), json={"items": []}).status_code == 422
    assert (
        client.post(
            notes_url(),
            json={"items": [{"tag": "wrong", "text": "내용"}]},
        ).status_code
        == 422
    )


def test_create_no_issue_note() -> None:
    client, _ = make_client()

    response = client.post(notes_url(), json={"noIssue": True})

    assert response.status_code == 201


def test_list_notes_passes_date_and_wraps_response() -> None:
    client, service = make_client()

    response = client.get(notes_url(), params={"date": "2026-11-19"})

    assert response.status_code == 200
    assert response.json()["date"] == "2026-11-19"
    assert len(response.json()["notes"]) == 1
    assert service.seen_date == date(2026, 11, 19)


def test_list_notes_without_date_uses_service_default() -> None:
    client, service = make_client()

    response = client.get(notes_url())

    assert response.json()["date"] == "2026-11-20"
    assert service.seen_date is None


def test_list_notes_rejects_invalid_date() -> None:
    client, _ = make_client()

    assert client.get(notes_url(), params={"date": "wrong"}).status_code == 422


def test_get_note() -> None:
    client, service = make_client()

    response = client.get(notes_url(f"/{service.note.id}"))

    assert response.status_code == 200
    assert response.json()["noteId"] == str(service.note.id)


def test_update_note_rejects_empty_and_null_values() -> None:
    client, service = make_client()
    url = notes_url(f"/{service.note.id}")

    assert client.patch(url, json={"summary": "요약"}).status_code == 200
    assert client.patch(url, json={}).status_code == 422
    assert client.patch(url, json={"items": None}).status_code == 422
    assert client.patch(url, json={"summary": None}).status_code == 422


def test_forbidden_update_returns_403() -> None:
    client, service = make_client()
    service.error = HandoverForbiddenError()

    response = client.patch(
        notes_url(f"/{service.note.id}"),
        json={"summary": "요약"},
    )

    assert response.status_code == 403


def test_not_found_errors_return_404() -> None:
    client, service = make_client()

    for error in (
        StoreNotFoundError(),
        HandoverNoteNotFoundError(),
        HandoverItemNotFoundError(),
    ):
        service.error = error
        assert client.get(notes_url(f"/{uuid4()}")).status_code == 404


def test_delete_note() -> None:
    client, service = make_client()

    response = client.delete(notes_url(f"/{service.note.id}"))

    assert response.status_code == 204
    assert service.deleted is True


def test_confirm_item() -> None:
    client, service = make_client()

    response = client.post(
        notes_url(f"/{service.note.id}/confirmations"),
        json={"itemId": str(service.item.id), "checked": True},
    )

    assert response.status_code == 200
    assert response.json()["items"][0]["checked"] is True
