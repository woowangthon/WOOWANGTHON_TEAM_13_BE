from datetime import date, datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict


def _to_camel(value: str) -> str:
    """응답 필드명을 camelCase로 변환합니다."""
    first, *rest = value.split("_")
    return first + "".join(word.capitalize() for word in rest)


class NotificationSchema(BaseModel):
    model_config = ConfigDict(
        alias_generator=_to_camel,
        populate_by_name=True,
        from_attributes=True,
    )


class NotificationTarget(NotificationSchema):
    kind: str
    id: UUID
    work_date: date | None = None


class NotificationItem(NotificationSchema):
    notification_id: str
    type: str
    title: str
    body: str
    created_at: datetime
    is_read: bool
    target: NotificationTarget


class ShiftBannerItem(NotificationSchema):
    note_id: UUID
    item_id: UUID
    tag: str
    text: str
    author_name: str
    work_date: date


class ShiftBannerResponse(NotificationSchema):
    work_date: date
    start_time: str
    end_time: str
    starts_at: datetime
    unchecked_count: int
    items: list[ShiftBannerItem]


class NotificationListResponse(NotificationSchema):
    banner: ShiftBannerResponse | None
    notifications: list[NotificationItem]
    unread_count: int
