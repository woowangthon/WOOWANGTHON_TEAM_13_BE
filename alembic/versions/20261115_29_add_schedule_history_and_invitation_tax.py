"""Preserve fixed schedule history and invitation tax settings.

Revision ID: 20261115_29
Revises: 20261114_28
"""

import sqlalchemy as sa

from alembic import op

revision = "20261115_29"
down_revision = "20261114_28"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "invitations",
        sa.Column("tax_type", sa.String(16), nullable=False, server_default="none"),
    )
    op.create_check_constraint(
        "ck_invitations_tax_type",
        "invitations",
        "tax_type IN ('none', '3.3', 'ins')",
    )
    op.add_column(
        "shift_templates",
        sa.Column(
            "effective_from", sa.Date(), nullable=False, server_default="0001-01-01"
        ),
    )
    op.add_column("shift_templates", sa.Column("deleted_from", sa.Date()))
    op.add_column(
        "shift_templates",
        sa.Column("history", sa.JSON(), nullable=False, server_default="[]"),
    )
    op.drop_constraint(
        "uq_shift_templates_store_name", "shift_templates", type_="unique"
    )
    op.create_index(
        "uq_shift_templates_store_name",
        "shift_templates",
        ["store_id", "name"],
        unique=True,
        postgresql_where=sa.text("deleted_from IS NULL"),
    )
    op.add_column(
        "schedule_assignments",
        sa.Column(
            "effective_from", sa.Date(), nullable=False, server_default="0001-01-01"
        ),
    )
    op.add_column("schedule_assignments", sa.Column("effective_until", sa.Date()))
    # Existing configuration has no previous versions. Keep its known contents,
    # but never project staff assignments before the membership's joining day.
    op.execute("""
        UPDATE schedule_assignments AS a
        SET effective_from = GREATEST(
            (s.created_at AT TIME ZONE 'Asia/Seoul')::date,
            (a.created_at AT TIME ZONE 'Asia/Seoul')::date,
            (SELECT (m.joined_at AT TIME ZONE 'Asia/Seoul')::date
             FROM memberships AS m
             WHERE m.store_id = a.store_id AND m.user_id = a.assignee_user_id)
        )
        FROM stores AS s
        WHERE a.store_id = s.id
    """)
    op.create_check_constraint(
        "ck_schedule_assignment_period",
        "schedule_assignments",
        "effective_until IS NULL OR effective_until >= effective_from",
    )
    op.drop_constraint(
        "uq_schedule_assignment_template_weekday_assignee",
        "schedule_assignments",
        type_="unique",
    )
    op.create_index(
        "uq_schedule_assignment_template_weekday_assignee",
        "schedule_assignments",
        ["template_id", "weekday", "assignee_user_id"],
        unique=True,
        postgresql_where=sa.text("effective_until IS NULL"),
    )


def downgrade() -> None:
    # Dropping history would make old payroll change again. Require an explicit
    # data-retention plan instead of silently discarding the temporal records.
    raise RuntimeError("Schedule history cannot be safely discarded automatically")
