from datetime import date, datetime
from uuid import UUID

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, Identity, String, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class BusinessVerification(Base):
    """국세청 API로 확인한 사업자등록정보 진위 결과입니다."""

    __tablename__ = "business_verifications"

    id: Mapped[int] = mapped_column(
        BigInteger,
        Identity(),
        primary_key=True,
    )
    requester_id: Mapped[UUID] = mapped_column(
        ForeignKey("users.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    business_registration_number: Mapped[str] = mapped_column(
        String(10),
        nullable=False,
    )
    owner_name: Mapped[str] = mapped_column(String(100), nullable=False)
    business_start_date: Mapped[date] = mapped_column(Date, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False)
    provider_message: Mapped[str] = mapped_column(String(500), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
