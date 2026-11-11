"""create schedule change notices

Revision ID: 20261112_25
Revises: 20261111_24
Create Date: 2026-11-12
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261112_25"
down_revision: str | None = "20261111_24"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedule_change_notices",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("change", sa.String(length=10), nullable=False),
        sa.Column("shifts_text", sa.String(length=300), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint(
            "change IN ('ADDED', 'REMOVED', 'CHANGED')",
            name="ck_schedule_change_notices_change",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_schedule_change_notices_store_user_created",
        "schedule_change_notices",
        ["store_id", "user_id", "created_at"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_schedule_change_notices_store_user_created",
        table_name="schedule_change_notices",
    )
    op.drop_table("schedule_change_notices")
