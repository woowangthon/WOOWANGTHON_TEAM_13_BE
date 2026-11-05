"""create assistant chat tables

Revision ID: 20261105_05
Revises: 20261105_04
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision: str = "20261105_05"
down_revision: str | None = "20261105_04"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """AI 사수 채팅방과 메시지 테이블을 생성합니다."""
    op.create_table(
        "assistant_chats",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("user_id", sa.Uuid(), nullable=False),
        sa.Column("last_message_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("last_message_text", sa.Text(), nullable=True),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            server_default=sa.text("now()"),
            nullable=False,
        ),
        sa.Column("deleted_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_assistant_chats_store_id"),
        "assistant_chats",
        ["store_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_assistant_chats_user_id"),
        "assistant_chats",
        ["user_id"],
        unique=False,
    )
    op.create_table(
        "assistant_messages",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("chat_id", sa.Uuid(), nullable=False),
        sa.Column("sender", sa.String(length=10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("answer_type", sa.String(length=20), nullable=True),
        sa.Column("sources", postgresql.JSONB(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["chat_id"],
            ["assistant_chats.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_assistant_messages_chat_id"),
        "assistant_messages",
        ["chat_id"],
        unique=False,
    )


def downgrade() -> None:
    """AI 사수 메시지와 채팅방 테이블을 제거합니다."""
    op.drop_index(
        op.f("ix_assistant_messages_chat_id"),
        table_name="assistant_messages",
    )
    op.drop_table("assistant_messages")
    op.drop_index(op.f("ix_assistant_chats_user_id"), table_name="assistant_chats")
    op.drop_index(op.f("ix_assistant_chats_store_id"), table_name="assistant_chats")
    op.drop_table("assistant_chats")
