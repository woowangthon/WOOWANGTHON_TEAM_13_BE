"""add store payday

Revision ID: 20261109_13
Revises: 20261109_12
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261109_13"
down_revision: str | None = "20261109_12"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stores",
        sa.Column("payday", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_stores_payday",
        "stores",
        "payday IS NULL OR payday BETWEEN 1 AND 28 OR payday = 31",
    )


def downgrade() -> None:
    op.drop_constraint("ck_stores_payday", "stores", type_="check")
    op.drop_column("stores", "payday")
