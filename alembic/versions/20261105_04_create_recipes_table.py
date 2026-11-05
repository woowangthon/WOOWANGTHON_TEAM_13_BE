"""create recipes table

Revision ID: 20261105_04
Revises: 20261105_03
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261105_04"
down_revision: str | None = "20261105_03"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """레시피 테이블과 매장 인덱스를 생성합니다."""
    op.create_table(
        "recipes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("category", sa.String(length=50), nullable=False),
        sa.Column("temp", sa.String(length=10), nullable=True),
        sa.Column("size", sa.String(length=20), nullable=True),
        sa.Column("ingredients", postgresql.JSONB(), nullable=False),
        sa.Column("steps", postgresql.JSONB(), nullable=False),
        sa.Column("memo", sa.Text(), nullable=True),
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
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_recipes_store_id"), "recipes", ["store_id"], unique=False)


def downgrade() -> None:
    """레시피 테이블과 매장 인덱스를 제거합니다."""
    op.drop_index(op.f("ix_recipes_store_id"), table_name="recipes")
    op.drop_table("recipes")
