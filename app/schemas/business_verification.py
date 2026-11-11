import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, field_validator


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

    @field_validator("business_registration_number")
    @classmethod
    def normalize_business_registration_number(cls, value: str) -> str:
        normalized = re.sub(r"[-\s]", "", value)
        if not re.fullmatch(r"\d{10}", normalized):
            raise ValueError("business registration number must have 10 digits")
        return normalized


class BusinessVerificationResponse(BusinessVerificationSchema):
    verification_id: int
    business_registration_number: str
    owner_name: str | None
    business_start_date: date | None
    status: str
    message: str
    created_at: datetime
