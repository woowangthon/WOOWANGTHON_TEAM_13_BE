"""create business verifications table

Revision ID: 20261110_15
Revises: 20261109_14
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261110_15"
down_revision: str | None = "20261109_14"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "business_verifications",
        sa.Column(
            "id",
            sa.BigInteger(),
            sa.Identity(),
            nullable=False,
        ),
        sa.Column("requester_id", sa.Uuid(), nullable=False),
        sa.Column(
            "business_registration_number",
            sa.String(length=10),
            nullable=False,
        ),
        sa.Column("owner_name", sa.String(length=100), nullable=False),
        sa.Column("business_start_date", sa.Date(), nullable=False),
        sa.Column("status", sa.String(length=16), nullable=False),
        sa.Column("provider_message", sa.String(length=500), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["requester_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_business_verifications_requester_id"),
        "business_verifications",
        ["requester_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_business_verifications_requester_id"),
        table_name="business_verifications",
    )
    op.drop_table("business_verifications")
