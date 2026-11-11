from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    String,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class NotificationRead(Base):
    """사용자가 매장 알림 화면을 마지막으로 연 시각입니다."""

    __tablename__ = "notification_reads"
    __table_args__ = (
        UniqueConstraint(
            "store_id", "user_id", name="uq_notification_reads_store_user"
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
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    last_read_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ScheduleChangeNotice(Base):
    """사장님이 하루 근무를 바꿔 근무가 달라진 직원에게 보낼 알림 기록입니다."""

    __tablename__ = "schedule_change_notices"
    __table_args__ = (
        CheckConstraint(
            "change IN ('ADDED', 'REMOVED', 'CHANGED')",
            name="ck_schedule_change_notices_change",
        ),
        Index(
            "ix_schedule_change_notices_store_user_created",
            "store_id",
            "user_id",
            "created_at",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="CASCADE"),
        nullable=False,
    )
    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    work_date: Mapped[date] = mapped_column(Date, nullable=False)
    change: Mapped[str] = mapped_column(String(10), nullable=False)
    shifts_text: Mapped[str] = mapped_column(String(300), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
