"""add daily schedule overrides

Revision ID: 20261111_22
Revises: 20261111_21
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261111_22"
down_revision: str | None = "20261111_21"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedule_day_overrides",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id",
            "work_date",
            name="uq_schedule_day_overrides_store_date",
        ),
    )
    op.create_index(
        "ix_schedule_day_overrides_store_id",
        "schedule_day_overrides",
        ["store_id"],
    )
    op.create_index(
        "ix_schedule_day_overrides_work_date",
        "schedule_day_overrides",
        ["work_date"],
    )

    op.create_table(
        "schedule_day_shifts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("day_override_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("assignee_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.func.now(),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assignee_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["day_override_id"],
            ["schedule_day_overrides.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["shift_templates.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "day_override_id",
            "template_id",
            "assignee_user_id",
            name="uq_schedule_day_shifts_override_template_assignee",
        ),
    )
    op.create_index(
        "ix_schedule_day_shifts_day_override_id",
        "schedule_day_shifts",
        ["day_override_id"],
    )
    op.create_index(
        "ix_schedule_day_shifts_template_id",
        "schedule_day_shifts",
        ["template_id"],
    )
    op.create_index(
        "ix_schedule_day_shifts_assignee_user_id",
        "schedule_day_shifts",
        ["assignee_user_id"],
    )


def downgrade() -> None:
    op.drop_table("schedule_day_shifts")
    op.drop_table("schedule_day_overrides")
