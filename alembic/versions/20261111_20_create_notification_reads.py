"""create notification reads

Revision ID: 20261111_20
Revises: 20261111_19
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261111_20"
down_revision: str | None = "20261111_19"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "notification_reads",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_read_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id",
            "user_id",
            name="uq_notification_reads_store_user",
        ),
    )
    op.create_index(
        "ix_notification_reads_store_id",
        "notification_reads",
        ["store_id"],
    )
    op.create_index(
        "ix_notification_reads_user_id",
        "notification_reads",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("ix_notification_reads_user_id", table_name="notification_reads")
    op.drop_index("ix_notification_reads_store_id", table_name="notification_reads")
    op.drop_table("notification_reads")
