from datetime import date
from uuid import UUID

from pydantic import BaseModel, ConfigDict
from pydantic.alias_generators import to_camel


class AssistantStatsSchema(BaseModel):
    model_config = ConfigDict(alias_generator=to_camel, populate_by_name=True)


class UnansweredQuestion(AssistantStatsSchema):
    question_id: UUID
    question: str
    staff_name: str


class UnansweredGroup(AssistantStatsSchema):
    category: str
    questions: list[UnansweredQuestion]


class AssistantStatsResponse(AssistantStatsSchema):
    week_start: date
    total: int
    answered: int
    last_week_rate: int | None
    unanswered: list[UnansweredGroup]
