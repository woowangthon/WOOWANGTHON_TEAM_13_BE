"""detach auth identities from withdrawn users

Revision ID: 20261114_27
Revises: 20261113_26
Create Date: 2026-11-14
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261114_27"
down_revision: str | None = "20261113_26"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "UPDATE users "
        "SET auth_user_id = gen_random_uuid() "
        "WHERE deleted_at IS NOT NULL"
    )


def downgrade() -> None:
    pass
