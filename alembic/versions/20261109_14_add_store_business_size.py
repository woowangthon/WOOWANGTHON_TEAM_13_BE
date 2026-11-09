"""add store business size

Revision ID: 20261109_14
Revises: 20261109_13
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261109_14"
down_revision: str | None = "20261109_13"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "stores",
        sa.Column("business_size", sa.String(length=20), nullable=True),
    )
    op.create_check_constraint(
        "ck_stores_business_size",
        "stores",
        "business_size IS NULL OR "
        "business_size IN ('UNDER_FIVE', 'FIVE_OR_MORE')",
    )


def downgrade() -> None:
    op.drop_constraint("ck_stores_business_size", "stores", type_="check")
    op.drop_column("stores", "business_size")
