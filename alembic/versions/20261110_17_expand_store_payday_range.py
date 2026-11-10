"""expand store payday range

Revision ID: 20261110_17
Revises: 20261110_16
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261110_17"
down_revision: str | None = "20261110_16"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "ck_stores_payday"


def upgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "stores", type_="check")
    op.create_check_constraint(
        CONSTRAINT_NAME,
        "stores",
        "payday IS NULL OR payday BETWEEN 1 AND 31",
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "stores", type_="check")
    op.create_check_constraint(
        CONSTRAINT_NAME,
        "stores",
        "payday IS NULL OR payday BETWEEN 1 AND 28 OR payday = 31",
    )
