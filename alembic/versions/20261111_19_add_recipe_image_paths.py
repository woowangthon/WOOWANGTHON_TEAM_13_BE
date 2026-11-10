"""add recipe image paths

Revision ID: 20261111_19
Revises: 20261110_18
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261111_19"
down_revision: str | None = "20261110_18"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "recipes",
        sa.Column("image_path", sa.String(length=300), nullable=True),
    )
    op.add_column(
        "recipes",
        sa.Column("recipe_image_path", sa.String(length=300), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("recipes", "recipe_image_path")
    op.drop_column("recipes", "image_path")
