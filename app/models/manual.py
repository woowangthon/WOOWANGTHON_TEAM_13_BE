from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, ForeignKey, String, Text, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class ManualCategory(Base):
    """매장 매뉴얼을 묶는 카테고리입니다."""

    __tablename__ = "manual_categories"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    name: Mapped[str] = mapped_column(String(50), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )


class Manual(Base):
    """매장 매뉴얼입니다."""

    __tablename__ = "manuals"

    id: Mapped[UUID] = mapped_column(Uuid, primary_key=True, default=uuid4)
    store_id: Mapped[UUID] = mapped_column(
        Uuid,
        ForeignKey("stores.id", ondelete="RESTRICT"),
        index=True,
        nullable=False,
    )
    category_id: Mapped[UUID | None] = mapped_column(
        Uuid,
        ForeignKey("manual_categories.id", ondelete="RESTRICT"),
        index=True,
        nullable=True,
    )
    icon: Mapped[str | None] = mapped_column(String(30), nullable=True)
    title: Mapped[str] = mapped_column(String(100), nullable=False)
    body: Mapped[str] = mapped_column(Text, nullable=False)
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
