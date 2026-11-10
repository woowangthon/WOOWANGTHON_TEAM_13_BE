"""link stores to business verifications

Revision ID: 20261110_16
Revises: 20261110_15
Create Date: 2026-11-10
"""

from collections.abc import Sequence

from alembic import op

revision: str = "20261110_16"
down_revision: str | None = "20261110_15"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

CONSTRAINT_NAME = "fk_stores_business_verification_id_business_verifications"


def upgrade() -> None:
    # 기존 개발 데이터의 임의 인증 ID는 유지하되 신규/변경 데이터부터 FK를 검사합니다.
    op.create_foreign_key(
        CONSTRAINT_NAME,
        "stores",
        "business_verifications",
        ["business_verification_id"],
        ["id"],
        ondelete="RESTRICT",
        postgresql_not_valid=True,
    )


def downgrade() -> None:
    op.drop_constraint(CONSTRAINT_NAME, "stores", type_="foreignkey")
