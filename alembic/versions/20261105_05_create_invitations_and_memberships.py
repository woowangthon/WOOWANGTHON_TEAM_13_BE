"""create invitations and memberships

Revision ID: 20261105_05
Revises: 20261105_04
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261105_05"
down_revision: str | None = "20261105_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """구성원, 초대 코드, 사용자별 실패 횟수 테이블을 생성합니다."""
    op.create_table(
        "memberships",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "role",
            sa.String(length=16),
            server_default="staff",
            nullable=False,
        ),
        sa.Column("staff_name", sa.String(length=50), nullable=False),
        sa.Column("hourly_wage", sa.Integer(), nullable=False),
        sa.Column(
            "joined_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("left_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "store_id",
            "user_id",
            name="uq_memberships_store_user",
        ),
    )
    op.create_index(
        op.f("ix_memberships_store_id"),
        "memberships",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_memberships_user_id"),
        "memberships",
        ["user_id"],
        unique=False,
    )

    op.create_table(
        "invitations",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("created_by_user_id", sa.Uuid(), nullable=False),
        sa.Column("code", sa.String(length=6), nullable=False),
        sa.Column("staff_name", sa.String(length=50), nullable=False),
        sa.Column("hourly_wage", sa.Integer(), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("revoked_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_by_user_id", sa.Uuid(), nullable=True),
        sa.ForeignKeyConstraint(
            ["accepted_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["created_by_user_id"],
            ["users.id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(
            ["store_id"],
            ["stores.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_invitations_code"),
        "invitations",
        ["code"],
        unique=True,
    )
    op.create_index(
        op.f("ix_invitations_store_id"),
        "invitations",
        ["store_id"],
        unique=False,
    )

    op.create_table(
        "invitation_attempts",
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column(
            "failure_count",
            sa.Integer(),
            server_default="0",
            nullable=False,
        ),
        sa.Column("locked_until", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "updated_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(
            ["user_id"],
            ["users.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("user_id"),
    )


def downgrade() -> None:
    """초대 코드와 구성원 관련 테이블을 제거합니다."""
    op.drop_table("invitation_attempts")
    op.drop_index(op.f("ix_invitations_store_id"), table_name="invitations")
    op.drop_index(op.f("ix_invitations_code"), table_name="invitations")
    op.drop_table("invitations")
    op.drop_index(op.f("ix_memberships_user_id"), table_name="memberships")
    op.drop_index(op.f("ix_memberships_store_id"), table_name="memberships")
    op.drop_table("memberships")
