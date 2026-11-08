"""create owner questions table

Revision ID: 20261108_09
Revises: 20261107_08
Create Date: 2026-11-08
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261108_09"
down_revision: str | None = "20261107_08"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """사장님께 물어보기 질문 테이블을 생성합니다."""
    op.create_table(
        "owner_questions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("message_id", sa.Uuid(), nullable=False),
        sa.Column("asked_by", sa.Uuid(), nullable=False),
        sa.Column("question", sa.Text(), nullable=False),
        sa.Column("status", sa.String(length=10), nullable=False),
        sa.Column("answer", sa.Text(), nullable=True),
        sa.Column("answered_by", sa.Uuid(), nullable=True),
        sa.Column("answered_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["assistant_chats.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(
            ["message_id"],
            ["assistant_messages.id"],
            ondelete="CASCADE",
        ),
        sa.ForeignKeyConstraint(["asked_by"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["answered_by"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("message_id"),
    )
    op.create_index(
        op.f("ix_owner_questions_store_id"),
        "owner_questions",
        ["store_id"],
        unique=False,
    )


def downgrade() -> None:
    """사장님께 물어보기 질문 테이블을 제거합니다."""
    op.drop_index(op.f("ix_owner_questions_store_id"), table_name="owner_questions")
    op.drop_table("owner_questions")
