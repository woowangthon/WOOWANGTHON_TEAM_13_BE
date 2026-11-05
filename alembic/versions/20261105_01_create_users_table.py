"""create users table

Revision ID: 20261105_01
Revises:
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261105_01"
down_revision: str | None = None
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """사용자 테이블과 인증 ID 인덱스를 생성합니다."""
    op.create_table(
        "users",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("auth_user_id", sa.Uuid(), nullable=False),
        sa.Column("nickname", sa.String(length=50), nullable=False),
        sa.Column("email", sa.String(length=320), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
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
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_users_auth_user_id"),
        "users",
        ["auth_user_id"],
        unique=True,
    )


def downgrade() -> None:
    """사용자 테이블과 인덱스를 제거합니다."""
    op.drop_index(op.f("ix_users_auth_user_id"), table_name="users")
    op.drop_table("users")
