from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    DateTime,
    ForeignKey,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class Membership(Base):
    """서비스 사용자와 매장을 연결하는 구성원 정보입니다."""

    __tablename__ = "memberships"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "user_id",
            name="uq_memberships_store_user",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    role: Mapped[str] = mapped_column(
        String(16),
        default="staff",
        server_default="staff",
        nullable=False,
    )
    staff_name: Mapped[str] = mapped_column(String(50), nullable=False)
    hourly_wage: Mapped[int] = mapped_column(Integer, nullable=False)
    joined_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    left_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
