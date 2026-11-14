from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import (
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    String,
    UniqueConstraint,
    Uuid,
    func,
    text,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class Invitation(Base):
    """매장에 합류할 직원을 위해 발급한 일회용 초대 코드입니다."""

    __tablename__ = "invitations"
    __table_args__ = (
        CheckConstraint(
            "tax_type IN ('none', '3.3', 'ins')", name="ck_invitations_tax_type"
        ),
        Index(
            "uq_invitations_available_store_staff_name",
            "store_id",
            "staff_name",
            unique=True,
            postgresql_where=text("revoked_at IS NULL AND accepted_at IS NULL"),
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="CASCADE"),
        index=True,
        nullable=False,
    )
    created_by_user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    code: Mapped[str] = mapped_column(
        String(6),
        unique=True,
        index=True,
        nullable=False,
    )
    staff_name: Mapped[str] = mapped_column(String(50), nullable=False)
    hourly_wage: Mapped[int] = mapped_column(Integer, nullable=False)
    tax_type: Mapped[str] = mapped_column(
        String(16), default="none", server_default="none", nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    revoked_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    accepted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    accepted_by_user_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=True,
    )
    schedule: Mapped[list["InvitationScheduleAssignment"]] = relationship(
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class InvitationScheduleAssignment(Base):
    """가입 전 초대 대상자에게 예약한 요일별 고정 근무입니다."""

    __tablename__ = "invitation_schedule_assignments"
    __table_args__ = (
        CheckConstraint(
            "weekday BETWEEN 0 AND 6",
            name="ck_invitation_schedule_assignment_weekday",
        ),
        UniqueConstraint(
            "invitation_id",
            "template_id",
            "weekday",
            name="uq_invitation_schedule_template_weekday",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    invitation_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("invitations.id", ondelete="CASCADE"),
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


class InvitationAttempt(Base):
    """사용자별 초대 코드 실패 횟수와 잠금 상태입니다."""

    __tablename__ = "invitation_attempts"

    user_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    failure_count: Mapped[int] = mapped_column(
        Integer,
        default=0,
        server_default="0",
        nullable=False,
    )
    locked_until: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
