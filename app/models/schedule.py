from datetime import date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    Time,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ShiftTemplate(Base):
    """매장에서 반복해서 사용하는 오픈/미들/마감 시간대입니다."""

    __tablename__ = "shift_templates"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_shift_template_time"),
        CheckConstraint(
            "headcount BETWEEN 1 AND 10", name="ck_shift_templates_headcount"
        ),
        UniqueConstraint("store_id", "name", name="uq_shift_templates_store_name"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    headcount: Mapped[int] = mapped_column(
        Integer, default=1, server_default="1", nullable=False
    )
    sort_order: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )


class ScheduleAssignment(Base):
    """매주 반복되는 요일·시간대별 고정 담당자입니다."""

    __tablename__ = "schedule_assignments"
    __table_args__ = (
        CheckConstraint(
            "weekday BETWEEN 0 AND 6",
            name="ck_schedule_assignment_weekday",
        ),
        UniqueConstraint(
            "template_id",
            "weekday",
            "assignee_user_id",
            name="uq_schedule_assignment_template_weekday_assignee",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    template_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("shift_templates.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    weekday: Mapped[int] = mapped_column(Integer, nullable=False)
    assignee_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    template: Mapped[ShiftTemplate] = relationship(lazy="joined")


class ScheduleAssignmentOverride(Base):
    """대타 수락으로 특정 날짜에만 바뀐 담당자입니다."""

    __tablename__ = "schedule_assignment_overrides"
    __table_args__ = (
        UniqueConstraint(
            "schedule_assignment_id",
            "work_date",
            name="uq_shift_override_assignment_date",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    schedule_assignment_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("schedule_assignments.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    assignee_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    substitute_request_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("substitute_requests.id", ondelete="RESTRICT"),
        unique=True,
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )


class SubstituteRequest(Base):
    """현재 근무자가 다른 근무자에게 보내는 단일 근무 대타 요청입니다."""

    __tablename__ = "substitute_requests"
    __table_args__ = (
        CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'CANCELLED')",
            name="ck_substitute_request_status",
        ),
        CheckConstraint(
            "requester_user_id <> target_user_id",
            name="ck_substitute_request_different_users",
        ),
        Index(
            "uq_substitute_pending_assignment_date",
            "schedule_assignment_id",
            "work_date",
            unique=True,
            postgresql_where=text("status = 'PENDING'"),
            sqlite_where=text("status = 'PENDING'"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    schedule_assignment_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("schedule_assignments.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    requester_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    target_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    status: Mapped[str] = mapped_column(
        String(16), default="PENDING", server_default="PENDING", nullable=False
    )
    target_read_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    responded_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )

    assignment: Mapped[ScheduleAssignment] = relationship(lazy="joined")
