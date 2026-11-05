"""create stores table

Revision ID: 20261105_02
Revises: 20261105_01
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261105_02"
down_revision: str | None = "20261105_01"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """매장 테이블과 소유자 인덱스를 생성합니다."""
    op.create_table(
        "stores",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("owner_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("address", sa.String(length=255), nullable=False),
        sa.Column("business_verification_id", sa.BigInteger(), nullable=True),
        sa.Column("photo_url", sa.String(length=2048), nullable=True),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["owner_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_stores_owner_id"),
        "stores",
        ["owner_id"],
        unique=False,
    )


def downgrade() -> None:
    """매장 테이블과 소유자 인덱스를 제거합니다."""
    op.drop_index(op.f("ix_stores_owner_id"), table_name="stores")
    op.drop_table("stores")
