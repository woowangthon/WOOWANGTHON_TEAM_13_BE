import json
from collections.abc import Mapping
from typing import Any
from uuid import uuid4

import pytest

from app.integrations.llm import LLMError
from app.services.owner_question import (
    MANUAL_BODY_MAX_LENGTH,
    MANUAL_DRAFT_SYSTEM_PROMPT,
    MANUAL_TITLE_MAX_LENGTH,
    OwnerQuestionNotFoundError,
    OwnerQuestionService,
    interpret_manual_draft,
)
from app.services.store_access import StoreAccessForbiddenError
from tests.unit.test_owner_question_service import (
    OWNER_ID,
    STAFF_ID,
    STORE_ID,
    FakeStoreAccess,
    Harness,
)


class FakeLLM:
    def __init__(self, events: list[str]) -> None:
        self.events = events
        self.result: Mapping[str, Any] = {
            "title": "청소도구 위치",
            "body": "창고 왼쪽 선반에 빗자루, 대걸레, 쓰레받기가 있어요.",
        }
        self.error: Exception | None = None
        self.calls: list[dict[str, Any]] = []

    async def generate_json(self, **kwargs: Any) -> Mapping[str, Any]:
        self.events.append("llm")
        self.calls.append(kwargs)
        if self.error is not None:
            raise self.error
        return self.result


class DraftHarness(Harness):
    def __init__(self) -> None:
        super().__init__()
        self.events: list[str] = []
        self.llm = FakeLLM(self.events)

        async def release() -> None:
            self.events.append("release")

        self.service = OwnerQuestionService(
            self.chats,
            self.repository,
            FakeStoreAccess(),
            self.categories,
            self.llm,
            release=release,
        )


@pytest.fixture
def harness() -> DraftHarness:
    return DraftHarness()


async def test_draft_sends_question_and_answer_as_data(harness: DraftHarness) -> None:
    question = await harness.ask(harness.not_found_exchange("청소도구 어딨어?"))
    harness.events.clear()

    draft = await harness.service.manual_draft(
        STORE_ID,
        question.id,
        OWNER_ID,
        "창고 왼쪽 선반에 빗자루 대걸레 쓰레받기 다 있어",
    )

    assert (draft.title, draft.body) == (
        "청소도구 위치",
        "창고 왼쪽 선반에 빗자루, 대걸레, 쓰레받기가 있어요.",
    )
    [call] = harness.llm.calls
    assert call["system_prompt"] == MANUAL_DRAFT_SYSTEM_PROMPT
    assert json.loads(call["user_prompt"]) == {
        "question": "청소도구 어딨어?",
        "answer": "창고 왼쪽 선반에 빗자루 대걸레 쓰레받기 다 있어",
    }
    assert harness.events == ["release", "llm"]


async def test_draft_saves_nothing(harness: DraftHarness) -> None:
    question = await harness.ask(harness.not_found_exchange())
    saved_before = list(harness.repository.saved_messages)

    await harness.service.manual_draft(STORE_ID, question.id, OWNER_ID, "답")

    assert question.status == "asked"
    assert harness.repository.saved_messages == saved_before
    assert harness.repository.saved_manuals == []


async def test_only_owner_can_draft(harness: DraftHarness) -> None:
    question = await harness.ask(harness.not_found_exchange())
    harness.events.clear()

    with pytest.raises(StoreAccessForbiddenError):
        await harness.service.manual_draft(STORE_ID, question.id, STAFF_ID, "답")
    assert harness.events == []


async def test_unknown_question_is_not_found(harness: DraftHarness) -> None:
    with pytest.raises(OwnerQuestionNotFoundError):
        await harness.service.manual_draft(STORE_ID, uuid4(), OWNER_ID, "답")
    assert harness.events == []


async def test_llm_failure_is_reported(harness: DraftHarness) -> None:
    question = await harness.ask(harness.not_found_exchange())
    harness.llm.error = LLMError("timeout")

    with pytest.raises(LLMError):
        await harness.service.manual_draft(STORE_ID, question.id, OWNER_ID, "답")


async def test_missing_llm_is_reported() -> None:
    harness = Harness()
    question = await harness.ask(harness.not_found_exchange())

    with pytest.raises(LLMError):
        await harness.service.manual_draft(STORE_ID, question.id, OWNER_ID, "답")


def test_interpret_trims_and_limits_lengths() -> None:
    draft = interpret_manual_draft(
        {
            "title": "  청소도구\n 위치  " + "가" * 200,
            "body": "  본문  " + "나" * 6000,
        }
    )

    assert draft.title is not None
    assert draft.body is not None
    assert draft.title.startswith("청소도구 위치")
    assert len(draft.title) <= MANUAL_TITLE_MAX_LENGTH
    assert draft.body.startswith("본문")
    assert len(draft.body) <= MANUAL_BODY_MAX_LENGTH


@pytest.mark.parametrize(
    "result",
    [
        {},
        {"title": 1, "body": "본문"},
        {"title": "제목", "body": None},
        {"title": "  ", "body": "본문"},
        {"title": "제목", "body": " "},
    ],
)
def test_interpret_rejects_invalid_results(result: Mapping[str, Any]) -> None:
    with pytest.raises(LLMError):
        interpret_manual_draft(result)
