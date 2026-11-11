"""add business status lookup

Revision ID: 20261111_24
Revises: 20261111_23
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261111_24"
down_revision: str | None = "20261111_23"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.alter_column(
        "business_verifications",
        "owner_name",
        existing_type=sa.String(length=100),
        nullable=True,
    )
    op.alter_column(
        "business_verifications",
        "business_start_date",
        existing_type=sa.Date(),
        nullable=True,
    )


def downgrade() -> None:
    op.execute(
        "UPDATE business_verifications SET owner_name = '' WHERE owner_name IS NULL"
    )
    op.execute(
        "UPDATE business_verifications SET business_start_date = '1970-01-01' "
        "WHERE business_start_date IS NULL"
    )
    op.alter_column(
        "business_verifications",
        "business_start_date",
        existing_type=sa.Date(),
        nullable=False,
    )
    op.alter_column(
        "business_verifications",
        "owner_name",
        existing_type=sa.String(length=100),
        nullable=False,
    )
