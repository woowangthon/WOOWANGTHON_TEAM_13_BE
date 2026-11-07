"""add available invitation unique index

Revision ID: 20261107_08
Revises: 20261105_07
Create Date: 2026-11-07
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261107_08"
down_revision: str | None = "20261105_07"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    """매장과 직원 이름별 활성 초대 코드를 하나로 제한합니다."""
    op.create_index(
        "uq_invitations_available_store_staff_name",
        "invitations",
        ["store_id", "staff_name"],
        unique=True,
        postgresql_where=sa.text(
            "revoked_at IS NULL AND accepted_at IS NULL"
        ),
    )


def downgrade() -> None:
    """활성 초대 코드 유니크 인덱스를 제거합니다."""
    op.drop_index(
        "uq_invitations_available_store_staff_name",
        table_name="invitations",
    )
