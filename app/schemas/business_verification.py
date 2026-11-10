import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


def _to_camel(value: str) -> str:
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class BusinessVerificationSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class BusinessVerificationCreateRequest(BusinessVerificationSchema):
    business_registration_number: str
    owner_name: str = Field(min_length=1, max_length=100)
    business_start_date: date

    @field_validator("business_registration_number")
    @classmethod
    def normalize_business_registration_number(cls, value: str) -> str:
        normalized = re.sub(r"[-\s]", "", value)
        if not re.fullmatch(r"\d{10}", normalized):
            raise ValueError("business registration number must have 10 digits")
        return normalized

    @field_validator("owner_name")
    @classmethod
    def normalize_owner_name(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("owner name must not be blank")
        return normalized


class BusinessVerificationResponse(BusinessVerificationSchema):
    verification_id: int
    business_registration_number: str
    owner_name: str
    business_start_date: date
    status: str
    message: str
    created_at: datetime
