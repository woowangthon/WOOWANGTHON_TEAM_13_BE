"""create manual tables

Revision ID: 20261105_03
Revises: 20261105_02
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261105_03"
down_revision: str | None = "20261105_02"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """매뉴얼 카테고리와 매뉴얼 테이블을 생성합니다."""
    op.create_table(
        "manual_categories",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_manual_categories_store_id"),
        "manual_categories",
        ["store_id"],
        unique=False,
    )
    op.create_table(
        "manuals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("category_id", sa.Uuid(), nullable=True),
        sa.Column("icon", sa.String(length=30), nullable=True),
        sa.Column("title", sa.String(length=100), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
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
            ["category_id"],
            ["manual_categories.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_manuals_category_id"),
        "manuals",
        ["category_id"],
        unique=False,
    )
    op.create_index(op.f("ix_manuals_store_id"), "manuals", ["store_id"], unique=False)


def downgrade() -> None:
    """매뉴얼 테이블과 매뉴얼 카테고리 테이블을 제거합니다."""
    op.drop_index(op.f("ix_manuals_store_id"), table_name="manuals")
    op.drop_index(op.f("ix_manuals_category_id"), table_name="manuals")
    op.drop_table("manuals")
    op.drop_index(
        op.f("ix_manual_categories_store_id"),
        table_name="manual_categories",
    )
    op.drop_table("manual_categories")
