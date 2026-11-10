"""create fixed schedules and substitutes

Revision ID: 20261110_18
Revises: 20261110_17
Create Date: 2026-11-10
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261110_18"
down_revision: str | None = "20261110_17"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "shift_templates",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=50), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("sort_order", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("end_time > start_time", name="ck_shift_template_time"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("store_id", "name", name="uq_shift_templates_store_name"),
    )
    op.create_index("ix_shift_templates_store_id", "shift_templates", ["store_id"])

    op.create_table(
        "fixed_shift_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.Column("assignee_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.CheckConstraint("weekday BETWEEN 0 AND 6", name="ck_fixed_shift_weekday"),
        sa.ForeignKeyConstraint(
            ["assignee_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["template_id"], ["shift_templates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "template_id",
            "weekday",
            "assignee_user_id",
            name="uq_fixed_shift_template_weekday_assignee",
        ),
    )
    op.create_index(
        "ix_fixed_shift_assignments_store_id", "fixed_shift_assignments", ["store_id"]
    )
    op.create_index(
        "ix_fixed_shift_assignments_template_id",
        "fixed_shift_assignments",
        ["template_id"],
    )
    op.create_index(
        "ix_fixed_shift_assignments_assignee_user_id",
        "fixed_shift_assignments",
        ["assignee_user_id"],
    )

    op.create_table(
        "substitute_requests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("fixed_assignment_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("requester_user_id", sa.Uuid(), nullable=False),
        sa.Column("target_user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "status", sa.String(length=16), server_default="PENDING", nullable=False
        ),
        sa.Column("target_read_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("responded_at", sa.DateTime(timezone=True), nullable=True),
        sa.CheckConstraint(
            "status IN ('PENDING', 'ACCEPTED', 'REJECTED', 'CANCELLED')",
            name="ck_substitute_request_status",
        ),
        sa.CheckConstraint(
            "requester_user_id <> target_user_id",
            name="ck_substitute_request_different_users",
        ),
        sa.ForeignKeyConstraint(
            ["fixed_assignment_id"], ["fixed_shift_assignments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["requester_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["target_user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_substitute_requests_store_id", "substitute_requests", ["store_id"]
    )
    op.create_index(
        "ix_substitute_requests_fixed_assignment_id",
        "substitute_requests",
        ["fixed_assignment_id"],
    )
    op.create_index(
        "ix_substitute_requests_work_date", "substitute_requests", ["work_date"]
    )
    op.create_index(
        "ix_substitute_requests_requester_user_id",
        "substitute_requests",
        ["requester_user_id"],
    )
    op.create_index(
        "ix_substitute_requests_target_user_id",
        "substitute_requests",
        ["target_user_id"],
    )
    op.create_index(
        "uq_substitute_pending_assignment_date",
        "substitute_requests",
        ["fixed_assignment_id", "work_date"],
        unique=True,
        postgresql_where=sa.text("status = 'PENDING'"),
    )

    op.create_table(
        "shift_assignment_overrides",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("fixed_assignment_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("assignee_user_id", sa.Uuid(), nullable=False),
        sa.Column("substitute_request_id", sa.Uuid(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["assignee_user_id"], ["users.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["fixed_assignment_id"], ["fixed_shift_assignments.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["substitute_request_id"], ["substitute_requests.id"], ondelete="RESTRICT"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("substitute_request_id"),
        sa.UniqueConstraint(
            "fixed_assignment_id",
            "work_date",
            name="uq_shift_override_assignment_date",
        ),
    )
    op.create_index(
        "ix_shift_assignment_overrides_fixed_assignment_id",
        "shift_assignment_overrides",
        ["fixed_assignment_id"],
    )
    op.create_index(
        "ix_shift_assignment_overrides_work_date",
        "shift_assignment_overrides",
        ["work_date"],
    )
    op.create_index(
        "ix_shift_assignment_overrides_assignee_user_id",
        "shift_assignment_overrides",
        ["assignee_user_id"],
    )


def downgrade() -> None:
    op.drop_table("shift_assignment_overrides")
    op.drop_table("substitute_requests")
    op.drop_table("fixed_shift_assignments")
    op.drop_table("shift_templates")
