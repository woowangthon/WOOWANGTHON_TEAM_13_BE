"""add fixed schedule configuration

Revision ID: 20261111_21
Revises: 20261111_20
Create Date: 2026-11-11
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261111_21"
down_revision: str | None = "20261111_20"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "shift_templates",
        sa.Column("headcount", sa.Integer(), server_default="1", nullable=False),
    )
    op.create_check_constraint(
        "ck_shift_templates_headcount",
        "shift_templates",
        "headcount BETWEEN 1 AND 10",
    )
    op.add_column(
        "stores",
        sa.Column("closed_weekdays", sa.JSON(), server_default="[]", nullable=False),
    )
    op.add_column(
        "stores",
        sa.Column(
            "closed_on_holidays",
            sa.Boolean(),
            server_default=sa.false(),
            nullable=False,
        ),
    )

    op.create_table(
        "invitation_schedule_assignments",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("invitation_id", sa.Uuid(), nullable=False),
        sa.Column("template_id", sa.Uuid(), nullable=False),
        sa.Column("weekday", sa.Integer(), nullable=False),
        sa.CheckConstraint(
            "weekday BETWEEN 0 AND 6",
            name="ck_invitation_schedule_assignment_weekday",
        ),
        sa.ForeignKeyConstraint(
            ["invitation_id"], ["invitations.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(
            ["template_id"], ["shift_templates.id"], ondelete="CASCADE"
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "invitation_id",
            "template_id",
            "weekday",
            name="uq_invitation_schedule_template_weekday",
        ),
    )
    op.create_index(
        "ix_invitation_schedule_assignments_invitation_id",
        "invitation_schedule_assignments",
        ["invitation_id"],
    )
    op.create_index(
        "ix_invitation_schedule_assignments_template_id",
        "invitation_schedule_assignments",
        ["template_id"],
    )


def downgrade() -> None:
    op.drop_table("invitation_schedule_assignments")
    op.drop_column("stores", "closed_on_holidays")
    op.drop_column("stores", "closed_weekdays")
    op.drop_constraint(
        "ck_shift_templates_headcount", "shift_templates", type_="check"
    )
    op.drop_column("shift_templates", "headcount")
