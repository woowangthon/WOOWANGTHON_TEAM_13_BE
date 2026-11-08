"""create schedule recommendations and schedules

Revision ID: 20261108_11
Revises: 20261108_10
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261108_11"
down_revision: str | None = "20261108_10"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "schedule_recommendations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("batch_id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("candidate_no", sa.Integer(), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column("maximum_weekly_hours", sa.Integer(), nullable=False),
        sa.Column("minimum_rest_minutes", sa.Integer(), nullable=False),
        sa.Column(
            "unfilled_slots",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "batch_id",
            "candidate_no",
            name="uq_schedule_recommendations_batch_candidate",
        ),
    )
    op.create_index(
        op.f("ix_schedule_recommendations_batch_id"),
        "schedule_recommendations",
        ["batch_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_schedule_recommendations_store_id"),
        "schedule_recommendations",
        ["store_id"],
        unique=False,
    )

    op.create_table(
        "recommendation_shifts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.Column("required_staff", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "end_time > start_time",
            name="ck_recommendation_shift_time",
        ),
        sa.CheckConstraint(
            "required_staff > 0",
            name="ck_recommendation_required_staff",
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["schedule_recommendations.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_recommendation_shifts_recommendation_id"),
        "recommendation_shifts",
        ["recommendation_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_recommendation_shifts_work_date"),
        "recommendation_shifts",
        ["work_date"],
        unique=False,
    )

    op.create_table(
        "recommendation_assignments",
        sa.Column("recommendation_shift_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["memberships.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_shift_id"],
            ["recommendation_shifts.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("recommendation_shift_id", "membership_id"),
    )
    op.create_index(
        op.f("ix_recommendation_assignments_membership_id"),
        "recommendation_assignments",
        ["membership_id"],
        unique=False,
    )

    op.create_table(
        "schedules",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("recommendation_id", sa.Uuid(), nullable=True),
        sa.Column("name", sa.String(length=100), nullable=False),
        sa.Column("start_date", sa.Date(), nullable=False),
        sa.Column("end_date", sa.Date(), nullable=False),
        sa.Column(
            "status",
            sa.String(length=16),
            server_default="draft",
            nullable=False,
        ),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
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
        sa.CheckConstraint(
            "status IN ('draft', 'published')",
            name="ck_schedules_status",
        ),
        sa.ForeignKeyConstraint(
            ["recommendation_id"],
            ["schedule_recommendations.id"],
            ondelete="SET NULL",
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("recommendation_id"),
    )
    op.create_index(
        op.f("ix_schedules_store_id"), "schedules", ["store_id"], unique=False
    )

    op.create_table(
        "schedule_shifts",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("schedule_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("start_time", sa.Time(), nullable=False),
        sa.Column("end_time", sa.Time(), nullable=False),
        sa.Column("role", sa.String(length=50), nullable=False),
        sa.CheckConstraint("end_time > start_time", name="ck_schedule_shift_time"),
        sa.ForeignKeyConstraint(
            ["schedule_id"], ["schedules.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_schedule_shifts_schedule_id"),
        "schedule_shifts",
        ["schedule_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_schedule_shifts_work_date"),
        "schedule_shifts",
        ["work_date"],
        unique=False,
    )

    op.create_table(
        "schedule_assignments",
        sa.Column("schedule_shift_id", sa.Uuid(), nullable=False),
        sa.Column("membership_id", sa.Uuid(), nullable=False),
        sa.ForeignKeyConstraint(
            ["membership_id"], ["memberships.id"], ondelete="RESTRICT"
        ),
        sa.ForeignKeyConstraint(
            ["schedule_shift_id"], ["schedule_shifts.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("schedule_shift_id", "membership_id"),
    )
    op.create_index(
        op.f("ix_schedule_assignments_membership_id"),
        "schedule_assignments",
        ["membership_id"],
        unique=False,
    )


def downgrade() -> None:
    op.drop_index(
        op.f("ix_schedule_assignments_membership_id"),
        table_name="schedule_assignments",
    )
    op.drop_table("schedule_assignments")
    op.drop_index(op.f("ix_schedule_shifts_work_date"), table_name="schedule_shifts")
    op.drop_index(op.f("ix_schedule_shifts_schedule_id"), table_name="schedule_shifts")
    op.drop_table("schedule_shifts")
    op.drop_index(op.f("ix_schedules_store_id"), table_name="schedules")
    op.drop_table("schedules")
    op.drop_index(
        op.f("ix_recommendation_assignments_membership_id"),
        table_name="recommendation_assignments",
    )
    op.drop_table("recommendation_assignments")
    op.drop_index(
        op.f("ix_recommendation_shifts_work_date"),
        table_name="recommendation_shifts",
    )
    op.drop_index(
        op.f("ix_recommendation_shifts_recommendation_id"),
        table_name="recommendation_shifts",
    )
    op.drop_table("recommendation_shifts")
    op.drop_index(
        op.f("ix_schedule_recommendations_store_id"),
        table_name="schedule_recommendations",
    )
    op.drop_index(
        op.f("ix_schedule_recommendations_batch_id"),
        table_name="schedule_recommendations",
    )
    op.drop_table("schedule_recommendations")
