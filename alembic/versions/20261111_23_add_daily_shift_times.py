"""add daily shift times

Revision ID: 20261111_23
Revises: 20261111_22
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261111_23"
down_revision: str | None = "20261111_22"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "schedule_day_shifts",
        sa.Column("start_time", sa.Time(), nullable=True),
    )
    op.add_column(
        "schedule_day_shifts",
        sa.Column("end_time", sa.Time(), nullable=True),
    )
    op.create_check_constraint(
        "ck_schedule_day_shifts_custom_time",
        "schedule_day_shifts",
        "(start_time IS NULL AND end_time IS NULL) OR "
        "(start_time IS NOT NULL AND end_time IS NOT NULL AND end_time > start_time)",
    )


def downgrade() -> None:
    op.drop_constraint(
        "ck_schedule_day_shifts_custom_time",
        "schedule_day_shifts",
        type_="check",
    )
    op.drop_column("schedule_day_shifts", "end_time")
    op.drop_column("schedule_day_shifts", "start_time")
