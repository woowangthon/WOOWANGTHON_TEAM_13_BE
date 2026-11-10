from pydantic import BaseModel, ConfigDict


def _to_camel(value: str) -> str:
    """응답 필드명을 camelCase로 변환합니다."""
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class StorePhotoResponse(BaseModel):
    model_config = ConfigDict(alias_generator=_to_camel, populate_by_name=True)

    photo_url: str
