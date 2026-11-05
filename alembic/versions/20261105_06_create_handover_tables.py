"""create handover tables

Revision ID: 20261105_06
Revises: 20261105_05
Create Date: 2026-11-05
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261105_06"
down_revision: str | None = "20261105_05"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """인수인계 노트와 항목 테이블을 생성합니다."""
    op.create_table(
        "handover_notes",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("store_id", sa.Uuid(), nullable=False),
        sa.Column("author_id", sa.Uuid(), nullable=False),
        sa.Column("work_date", sa.Date(), nullable=False),
        sa.Column("raw_text", sa.Text(), nullable=False),
        sa.Column("no_issue", sa.Boolean(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=False),
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
        sa.ForeignKeyConstraint(["author_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(["store_id"], ["stores.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
    )
    for column in ("author_id", "store_id", "work_date"):
        op.create_index(
            op.f(f"ix_handover_notes_{column}"),
            "handover_notes",
            [column],
            unique=False,
        )
    op.create_table(
        "handover_items",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("note_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("tag", sa.String(length=10), nullable=False),
        sa.Column("text", sa.Text(), nullable=False),
        sa.Column("checked", sa.Boolean(), nullable=False),
        sa.Column("checked_by_id", sa.Uuid(), nullable=True),
        sa.Column("checked_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["checked_by_id"], ["users.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["note_id"],
            ["handover_notes.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_handover_items_note_id"),
        "handover_items",
        ["note_id"],
        unique=False,
    )


def downgrade() -> None:
    """인수인계 항목과 노트 테이블을 제거합니다."""
    op.drop_index(op.f("ix_handover_items_note_id"), table_name="handover_items")
    op.drop_table("handover_items")
    for column in ("work_date", "store_id", "author_id"):
        op.drop_index(
            op.f(f"ix_handover_notes_{column}"),
            table_name="handover_notes",
        )
    op.drop_table("handover_notes")
