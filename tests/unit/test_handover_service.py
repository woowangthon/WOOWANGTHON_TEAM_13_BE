from collections.abc import Mapping
from datetime import date
from typing import Any
from uuid import UUID, uuid4

import pytest

from app.integrations.llm import LLMError
from app.models.handover import HandoverNote
from app.schemas.handover import (
    HandoverConfirmationRequest,
    HandoverNoteCreateRequest,
    HandoverNoteUpdateRequest,
)
from app.services.handover import (
    HandoverForbiddenError,
    HandoverItemNotFoundError,
    HandoverNoteNotFoundError,
    HandoverService,
    interpret_draft,
    today_kst,
)
from app.services.store import StoreNotFoundError
from app.services.store_access import StoreAccessForbiddenError

STORE_ID = uuid4()
OWNER_ID = uuid4()
STAFF_ID = uuid4()
OTHER_STAFF_ID = uuid4()


class FakeHandoverRepository:
    def __init__(self) -> None:
        self.notes: list[HandoverNote] = []

    async def list_by_date(
        self,
        store_id: UUID,
        work_date: date,
    ) -> list[HandoverNote]:
        return [
            note
            for note in self.notes
            if note.store_id == store_id
            and note.work_date == work_date
            and note.deleted_at is None
        ]

    async def get_by_id_and_store_id(
        self,
        note_id: UUID,
        store_id: UUID,
    ) -> HandoverNote | None:
        return next(
            (
                note
                for note in self.notes
                if note.id == note_id
                and note.store_id == store_id
                and note.deleted_at is None
            ),
            None,
        )

    async def save(self, note: HandoverNote) -> HandoverNote:
        if note.id is None:
            note.id = uuid4()
            self.notes.append(note)
        for item in note.items:
            if item.id is None:
                item.id = uuid4()
                item.checked = False
        return note


class FakeStoreAccess:
    async def ensure_owner(self, store_id: UUID, user_id: UUID) -> None:
        await self.ensure_member(store_id, user_id)
        if user_id != OWNER_ID:
            raise StoreAccessForbiddenError

    async def ensure_member(self, store_id: UUID, user_id: UUID) -> None:
        if store_id != STORE_ID or user_id not in (
            OWNER_ID,
            STAFF_ID,
            OTHER_STAFF_ID,
        ):
            raise StoreNotFoundError


class FakeLLM:
    def __init__(self) -> None:
        self.result: Mapping[str, Any] = {"summary": "", "items": []}
        self.prompts: list[str] = []

    async def generate_json(
        self,
        *,
        system_prompt: str,
        user_prompt: str,
        response_schema: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        self.prompts.append(user_prompt)
        return self.result


@pytest.fixture
def repository() -> FakeHandoverRepository:
    return FakeHandoverRepository()


@pytest.fixture
def llm() -> FakeLLM:
    return FakeLLM()


@pytest.fixture
def service(repository: FakeHandoverRepository, llm: FakeLLM) -> HandoverService:
    return HandoverService(repository, FakeStoreAccess(), llm)


def create_request(**overrides: object) -> HandoverNoteCreateRequest:
    values: dict[str, object] = {
        "rawText": "딸기청 1병 남았어요",
        "summary": "딸기청 1병 남음",
        "items": [
            {"tag": "stock", "text": "딸기청 1병 남음"},
            {"tag": "etc", "text": "제빙기 소음"},
        ],
    }
    return HandoverNoteCreateRequest.model_validate({**values, **overrides})


async def make_note(service: HandoverService) -> HandoverNote:
    return await service.create(STORE_ID, STAFF_ID, create_request())


def test_interpret_draft_cleans_items() -> None:
    draft = interpret_draft(
        {
            "summary": " 요약 ",
            "items": [
                {"tag": "stock", "text": " 우유 부족 "},
                {"tag": "unknown", "text": "기타 내용"},
                {"tag": "etc", "text": "  "},
                "wrong",
            ],
        }
    )

    assert draft.summary == "요약"
    assert draft.items == [
        {"tag": "stock", "text": "우유 부족"},
        {"tag": "etc", "text": "기타 내용"},
    ]


def test_invalid_draft_raises_llm_error() -> None:
    with pytest.raises(LLMError):
        interpret_draft({"summary": "요약", "items": "wrong"})


async def test_create_draft_saves_nothing(
    repository: FakeHandoverRepository,
    llm: FakeLLM,
    service: HandoverService,
) -> None:
    llm.result = {"summary": "요약", "items": [{"tag": "etc", "text": "내용"}]}

    draft = await service.create_draft(STORE_ID, STAFF_ID, "줄글")

    assert draft.items == [{"tag": "etc", "text": "내용"}]
    assert "줄글" in llm.prompts[0]
    assert repository.notes == []


async def test_stranger_cannot_create_draft_or_note(
    llm: FakeLLM,
    service: HandoverService,
) -> None:
    with pytest.raises(StoreNotFoundError):
        await service.create_draft(STORE_ID, uuid4(), "줄글")
    with pytest.raises(StoreNotFoundError):
        await service.create(STORE_ID, uuid4(), create_request())
    assert llm.prompts == []


async def test_create_keeps_raw_text_and_item_order(
    service: HandoverService,
) -> None:
    note = await make_note(service)

    assert note.author_id == STAFF_ID
    assert note.raw_text == "딸기청 1병 남았어요"
    assert note.work_date == today_kst()
    assert [item.position for item in note.items] == [0, 1]


def test_no_issue_clears_content() -> None:
    request = create_request(noIssue=True)

    assert request.raw_text == ""
    assert request.summary == ""
    assert request.items == []


def test_note_with_issue_requires_items() -> None:
    with pytest.raises(ValueError):
        create_request(items=[])


async def test_list_defaults_to_today(service: HandoverService) -> None:
    note = await make_note(service)

    target, notes = await service.list_by_date(STORE_ID, STAFF_ID, None)

    assert target == today_kst()
    assert notes == [note]


async def test_list_uses_requested_date(service: HandoverService) -> None:
    await make_note(service)

    target, notes = await service.list_by_date(
        STORE_ID,
        STAFF_ID,
        date(2020, 1, 1),
    )

    assert target == date(2020, 1, 1)
    assert notes == []


async def test_update_keeps_check_state_of_existing_items(
    service: HandoverService,
) -> None:
    note = await make_note(service)
    kept, removed = note.items
    await service.confirm(
        STORE_ID,
        note.id,
        OTHER_STAFF_ID,
        HandoverConfirmationRequest(item_id=kept.id, checked=True),
    )

    updated = await service.update(
        STORE_ID,
        note.id,
        STAFF_ID,
        HandoverNoteUpdateRequest.model_validate(
            {
                "items": [
                    {"itemId": None, "tag": "etc", "text": "빨대 입고"},
                    {"itemId": str(kept.id), "tag": "stock", "text": "수정된 내용"},
                ]
            }
        ),
    )

    assert [item.text for item in updated.items] == ["빨대 입고", "수정된 내용"]
    assert [item.position for item in updated.items] == [0, 1]
    assert updated.items[1].checked is True
    assert updated.items[1].checked_by_id == OTHER_STAFF_ID
    assert removed not in updated.items


async def test_update_rejects_item_of_other_note(service: HandoverService) -> None:
    note = await make_note(service)

    with pytest.raises(HandoverItemNotFoundError):
        await service.update(
            STORE_ID,
            note.id,
            STAFF_ID,
            HandoverNoteUpdateRequest.model_validate(
                {"items": [{"itemId": str(uuid4()), "tag": "etc", "text": "내용"}]}
            ),
        )


async def test_owner_can_edit_but_other_staff_cannot(
    service: HandoverService,
) -> None:
    note = await make_note(service)
    request = HandoverNoteUpdateRequest.model_validate({"summary": "새 요약"})

    updated = await service.update(STORE_ID, note.id, OWNER_ID, request)
    assert updated.summary == "새 요약"

    with pytest.raises(HandoverForbiddenError):
        await service.update(STORE_ID, note.id, OTHER_STAFF_ID, request)
    with pytest.raises(HandoverForbiddenError):
        await service.delete(STORE_ID, note.id, OTHER_STAFF_ID)


async def test_deleted_note_is_hidden(service: HandoverService) -> None:
    note = await make_note(service)

    await service.delete(STORE_ID, note.id, STAFF_ID)

    with pytest.raises(HandoverNoteNotFoundError):
        await service.get(STORE_ID, note.id, STAFF_ID)


async def test_confirm_and_uncheck_single_item(service: HandoverService) -> None:
    note = await make_note(service)
    item = note.items[0]

    await service.confirm(
        STORE_ID,
        note.id,
        OTHER_STAFF_ID,
        HandoverConfirmationRequest(item_id=item.id, checked=True),
    )
    assert item.checked is True
    assert item.checked_by_id == OTHER_STAFF_ID
    assert item.checked_at is not None
    assert note.items[1].checked is False

    await service.confirm(
        STORE_ID,
        note.id,
        OTHER_STAFF_ID,
        HandoverConfirmationRequest(item_id=item.id, checked=False),
    )
    assert item.checked is False
    assert item.checked_by_id is None
    assert item.checked_at is None


async def test_confirm_without_item_checks_whole_note(
    service: HandoverService,
) -> None:
    note = await make_note(service)

    await service.confirm(
        STORE_ID,
        note.id,
        STAFF_ID,
        HandoverConfirmationRequest(),
    )

    assert all(item.checked for item in note.items)


async def test_confirm_unknown_item_is_not_found(service: HandoverService) -> None:
    note = await make_note(service)

    with pytest.raises(HandoverItemNotFoundError):
        await service.confirm(
            STORE_ID,
            note.id,
            STAFF_ID,
            HandoverConfirmationRequest(item_id=uuid4()),
        )


async def test_create_draft_releases_db_before_llm(
    repository: FakeHandoverRepository,
    llm: FakeLLM,
) -> None:
    events: list[str] = []

    async def release() -> None:
        events.append("release")

    original = llm.generate_json

    async def tracked(**kwargs: Any) -> Mapping[str, Any]:
        events.append("llm")
        return await original(**kwargs)

    llm.generate_json = tracked  # type: ignore[method-assign]
    service = HandoverService(repository, FakeStoreAccess(), llm, release=release)

    await service.create_draft(STORE_ID, STAFF_ID, "줄글")

    assert events == ["release", "llm"]
