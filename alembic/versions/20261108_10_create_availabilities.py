"""create availabilities

Revision ID: 20261108_10
Revises: 20261108_09
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261108_10"
down_revision: str | None = "20261108_09"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """월별 근무 가능 시간과 날짜별 표시를 저장합니다."""
    op.create_table(
        "availabilities",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.Column("month", sa.Date(), nullable=False),
        sa.Column("memo", sa.Text(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["membership_id"],
            ["memberships.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id",
            "membership_id",
            "month",
            name="uq_availabilities_store_member_month",
        ),
    )
    op.create_index(
        op.f("ix_availabilities_membership_id"),
        "availabilities",
        ["membership_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_availabilities_store_id"),
        "availabilities",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        "ix_availabilities_store_month",
        "availabilities",
        ["store_id", "month"],
        unique=False,
    )

    op.create_table(
        "availability_days",
        sa.Column("availability_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=11), nullable=False),
        sa.CheckConstraint(
            "status IN ('available', 'unavailable')",
            name="ck_availability_days_status",
        ),
        sa.ForeignKeyConstraint(
            ["availability_id"],
            ["availabilities.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("availability_id", "work_date"),
    )
    op.create_index(
        "ix_availability_days_work_date",
        "availability_days",
        ["work_date"],
        unique=False,
    )


def downgrade() -> None:
    """근무 가능 시간 테이블을 제거합니다."""
    op.drop_index("ix_availability_days_work_date", table_name="availability_days")
    op.drop_table("availability_days")
    op.drop_index("ix_availabilities_store_month", table_name="availabilities")
    op.drop_index(
        op.f("ix_availabilities_store_id"),
        table_name="availabilities",
    )
    op.drop_index(
        op.f("ix_availabilities_membership_id"),
        table_name="availabilities",
    )
    op.drop_table("availabilities")
