"""add member payroll settings

Revision ID: 20261109_12
Revises: 20261108_11
Create Date: 2026-11-09
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261109_12"
down_revision: str | None = "20261108_11"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "memberships",
        sa.Column(
            "tax_type",
            sa.String(length=16),
            server_default="none",
            nullable=False,
        ),
    )
    op.add_column(
        "memberships",
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
    )
    op.create_check_constraint(
        "ck_memberships_tax_type",
        "memberships",
        "tax_type IN ('none', '3.3', 'ins')",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_memberships_tax_type",
        "memberships",
        type_="check",
    )
    op.drop_column("memberships", "updated_at")
    op.drop_column("memberships", "tax_type")
