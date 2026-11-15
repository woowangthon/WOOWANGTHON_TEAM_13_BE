"""Allow the reusable demo business number on multiple active stores.

Revision ID: 20261115_30
Revises: 20261115_29
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261115_30"
down_revision: str | None = "20261115_29"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_stores_active_business_registration_number"
REUSABLE_DEMO_BUSINESS_REGISTRATION_NUMBER = "0000000000"
ACTIVE_UNIQUE_PREDICATE = (
    "deleted_at IS NULL "
    "AND business_registration_number IS NOT NULL "
    "AND business_registration_number <> "
    f"'{REUSABLE_DEMO_BUSINESS_REGISTRATION_NUMBER}'"
)


def upgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="stores")
    op.create_index(
        INDEX_NAME,
        "stores",
        ["business_registration_number"],
        unique=True,
        postgresql_where=sa.text(ACTIVE_UNIQUE_PREDICATE),
    )


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="stores")
    # 재사용 허용 기간에 추가된 테스트 매장은 인증 연결을 보존하되, 기존 인덱스와
    # 충돌하지 않도록 번호별 최초 활성 매장 외의 비정규화 번호만 비웁니다.
    op.execute(
        "WITH ranked AS ("
        "SELECT id, ROW_NUMBER() OVER (ORDER BY created_at, id) AS row_number "
        "FROM stores "
        "WHERE deleted_at IS NULL "
        "AND business_registration_number = "
        f"'{REUSABLE_DEMO_BUSINESS_REGISTRATION_NUMBER}'"
        ") "
        "UPDATE stores AS s "
        "SET business_registration_number = NULL "
        "FROM ranked "
        "WHERE s.id = ranked.id AND ranked.row_number > 1"
    )
    op.create_index(
        INDEX_NAME,
        "stores",
        ["business_registration_number"],
        unique=True,
        postgresql_where=sa.text(
            "deleted_at IS NULL AND business_registration_number IS NOT NULL"
        ),
    )
