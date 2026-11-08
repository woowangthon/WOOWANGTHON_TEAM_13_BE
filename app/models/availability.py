from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

AVAILABLE = "available"
UNAVAILABLE = "unavailable"


class Availability(Base):
    """구성원이 한 달 단위로 제출한 근무 가능 시간입니다."""

    __tablename__ = "availabilities"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "membership_id",
            "month",
            name="uq_availabilities_store_member_month",
        ),
        Index("ix_availabilities_store_month", "store_id", "month"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    membership_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("memberships.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    month: Mapped[date] = mapped_column(Date, nullable=False)
    memo: Mapped[str] = mapped_column(Text, default="", nullable=False)
    submitted_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    days: Mapped[list["AvailabilityDay"]] = relationship(
        cascade="all, delete-orphan",
        order_by="AvailabilityDay.work_date",
        lazy="selectin",
    )


class AvailabilityDay(Base):
    """제출한 월에서 사용자가 가능 또는 불가로 표시한 날짜입니다."""

    __tablename__ = "availability_days"
    __table_args__ = (
        CheckConstraint(
            "status IN ('available', 'unavailable')",
            name="ck_availability_days_status",
        ),
    )

    availability_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("availabilities.id", ondelete="CASCADE"),
        primary_key=True,
    )
    work_date: Mapped[date] = mapped_column(Date, primary_key=True, index=True)
    status: Mapped[str] = mapped_column(String(11), nullable=False)
