from datetime import date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import (
    JSON,
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
        Index(
            "uq_shift_templates_store_name",
            "store_id",
            "name",
            unique=True,
            postgresql_where=text("deleted_from IS NULL"),
            sqlite_where=text("deleted_from IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    effective_from: Mapped[date] = mapped_column(
        Date, default=date.min, server_default="0001-01-01", nullable=False
    )
    deleted_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    history: Mapped[list[dict[str, str | int]]] = mapped_column(
        JSON, default=list, server_default="[]", nullable=False
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
        CheckConstraint(
            "effective_until IS NULL OR effective_until >= effective_from",
            name="ck_schedule_assignment_period",
        ),
        Index(
            "uq_schedule_assignment_template_weekday_assignee",
            "template_id",
            "weekday",
            "assignee_user_id",
            unique=True,
            postgresql_where=text("effective_until IS NULL"),
            sqlite_where=text("effective_until IS NULL"),
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
    effective_from: Mapped[date] = mapped_column(
        Date, default=date.min, server_default="0001-01-01", nullable=False
    )
    effective_until: Mapped[date | None] = mapped_column(Date, nullable=True)
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


class ScheduleDayOverride(Base):
    """사장님이 특정 날짜의 근무 목록을 직접 교체한 기록입니다."""

    __tablename__ = "schedule_day_overrides"
    __table_args__ = (
        UniqueConstraint(
            "store_id",
            "work_date",
            name="uq_schedule_day_overrides_store_date",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    shifts: Mapped[list["ScheduleDayShift"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
        order_by="ScheduleDayShift.id",
    )


class ScheduleDayShift(Base):
    """날짜별 교체 목록 안의 실제 근무 한 건입니다."""

    __tablename__ = "schedule_day_shifts"
    __table_args__ = (
        UniqueConstraint(
            "day_override_id",
            "template_id",
            "assignee_user_id",
            name="uq_schedule_day_shifts_override_template_assignee",
        ),
        CheckConstraint(
            "(start_time IS NULL AND end_time IS NULL) OR "
            "(start_time IS NOT NULL AND end_time IS NOT NULL "
            "AND end_time > start_time)",
            name="ck_schedule_day_shifts_custom_time",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    day_override_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("schedule_day_overrides.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    template_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("shift_templates.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    assignee_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    start_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    end_time: Mapped[time | None] = mapped_column(Time, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )

    template: Mapped[ShiftTemplate] = relationship(lazy="joined")


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
