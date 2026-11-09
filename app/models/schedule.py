from datetime import date, datetime, time
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Time,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class ScheduleRecommendation(Base):
    """규칙 엔진이 만든 하나의 추천 스케줄 후보입니다."""

    __tablename__ = "schedule_recommendations"
    __table_args__ = (
        UniqueConstraint(
            "batch_id",
            "candidate_no",
            name="uq_schedule_recommendations_batch_candidate",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    batch_id: Mapped[UUID] = mapped_column(Uuid, index=True, nullable=False)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    candidate_no: Mapped[int] = mapped_column(Integer, nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    maximum_weekly_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    minimum_rest_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    unfilled_slots: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    shifts: Mapped[list["RecommendationShift"]] = relationship(
        cascade="all, delete-orphan",
        order_by="RecommendationShift.work_date, RecommendationShift.start_time",
        lazy="selectin",
    )


class RecommendationShift(Base):
    """추천 후보 안에서 필요한 하나의 근무 시간대입니다."""

    __tablename__ = "recommendation_shifts"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_recommendation_shift_time"),
        CheckConstraint("required_staff > 0", name="ck_recommendation_required_staff"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    recommendation_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("schedule_recommendations.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="", nullable=False)
    required_staff: Mapped[int] = mapped_column(Integer, nullable=False)

    assignments: Mapped[list["RecommendationAssignment"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class RecommendationAssignment(Base):
    """추천 근무 시간대에 배정된 구성원입니다."""

    __tablename__ = "recommendation_assignments"

    recommendation_shift_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("recommendation_shifts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    membership_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("memberships.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )


class Schedule(Base):
    """사장님이 추천 후보를 선택해 등록한 실제 스케줄입니다."""

    __tablename__ = "schedules"
    __table_args__ = (
        CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_schedules_status",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    recommendation_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("schedule_recommendations.id", ondelete="SET NULL"),
        unique=True,
        nullable=True,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    start_date: Mapped[date] = mapped_column(Date, nullable=False)
    end_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(
        String(16),
        default="draft",
        server_default="draft",
        nullable=False,
    )
    published_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
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

    shifts: Mapped[list["ScheduleShift"]] = relationship(
        cascade="all, delete-orphan",
        order_by="ScheduleShift.work_date, ScheduleShift.start_time",
        lazy="selectin",
    )


class ScheduleShift(Base):
    """확정 스케줄의 근무 시간대입니다."""

    __tablename__ = "schedule_shifts"
    __table_args__ = (
        CheckConstraint("end_time > start_time", name="ck_schedule_shift_time"),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    schedule_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("schedules.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    work_date: Mapped[date] = mapped_column(Date, index=True, nullable=False)
    start_time: Mapped[time] = mapped_column(Time, nullable=False)
    end_time: Mapped[time] = mapped_column(Time, nullable=False)
    role: Mapped[str] = mapped_column(String(50), default="", nullable=False)

    assignments: Mapped[list["ScheduleAssignment"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class ScheduleAssignment(Base):
    """확정 근무 시간대에 배정된 구성원입니다."""

    __tablename__ = "schedule_assignments"

    schedule_shift_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("schedule_shifts.id", ondelete="CASCADE"),
        primary_key=True,
    )
    membership_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("memberships.id", ondelete="RESTRICT"),
        primary_key=True,
        index=True,
    )
