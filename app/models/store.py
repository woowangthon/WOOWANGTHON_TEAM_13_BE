from datetime import datetime
from typing import TYPE_CHECKING
from uuid import UUID, uuid4

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Uuid,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.schedule import ShiftTemplate


class Store(Base):
    """서비스에서 관리하는 매장입니다."""

    __tablename__ = "stores"
    __table_args__ = (
        CheckConstraint(
            "payday IS NULL OR payday BETWEEN 1 AND 31",
            name="ck_stores_payday",
        ),
        CheckConstraint(
            "business_size IS NULL OR business_size IN ('UNDER_FIVE', 'FIVE_OR_MORE')",
            name="ck_stores_business_size",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    owner_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(100), nullable=False)
    address: Mapped[str] = mapped_column(String(255), nullable=False)
    business_verification_id: Mapped[int | None] = mapped_column(
        BigInteger,
        ForeignKey("business_verifications.id", ondelete="RESTRICT"),
        nullable=True,
    )
    photo_url: Mapped[str | None] = mapped_column(String(2048), nullable=True)
    payday: Mapped[int | None] = mapped_column(Integer, nullable=True)
    business_size: Mapped[str | None] = mapped_column(String(20), nullable=True)
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
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
    )
    shift_templates: Mapped[list["ShiftTemplate"]] = relationship(
        cascade="all, delete-orphan",
        lazy="raise",
    )
