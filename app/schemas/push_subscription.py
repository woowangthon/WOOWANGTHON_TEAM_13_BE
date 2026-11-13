from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class PushSubscriptionSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class PushKeys(PushSubscriptionSchema):
    p256dh: str = Field(min_length=1, max_length=200)
    auth: str = Field(min_length=1, max_length=100)


class PushSubscriptionCreateRequest(PushSubscriptionSchema):
    endpoint: str = Field(min_length=1, max_length=2048)
    keys: PushKeys


class PushSubscriptionDeleteRequest(PushSubscriptionSchema):
    endpoint: str = Field(min_length=1, max_length=2048)


class PushSubscriptionResponse(PushSubscriptionSchema):
    subscription_id: UUID
