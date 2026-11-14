"""enforce one active store per business registration number

Revision ID: 20261114_28
Revises: 20261114_27
Create Date: 2026-11-14
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "20261114_28"
down_revision: str | None = "20261114_27"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

INDEX_NAME = "uq_stores_active_business_registration_number"


def upgrade() -> None:
    op.add_column(
        "stores",
        sa.Column(
            "business_registration_number",
            sa.String(length=10),
            nullable=True,
        ),
    )

    # 삭제된 매장은 활성 유니크 인덱스 대상이 아니므로 모두 원래 번호를 보존합니다.
    op.execute(
        "UPDATE stores AS s "
        "SET business_registration_number = bv.business_registration_number "
        "FROM business_verifications AS bv "
        "WHERE s.business_verification_id = bv.id "
        "AND s.deleted_at IS NOT NULL"
    )

    # 이미 존재하는 활성 중복은 삭제하지 않습니다. 번호별 최초 매장만 채우고 나머지는
    # NULL로 남겨 마이그레이션 후 새 중복 생성부터 차단합니다.
    op.execute(
        "WITH ranked AS ("
        "SELECT s.id, bv.business_registration_number, "
        "ROW_NUMBER() OVER ("
        "PARTITION BY bv.business_registration_number "
        "ORDER BY s.created_at, s.id"
        ") AS row_number "
        "FROM stores AS s "
        "JOIN business_verifications AS bv "
        "ON bv.id = s.business_verification_id "
        "WHERE s.deleted_at IS NULL"
        ") "
        "UPDATE stores AS s "
        "SET business_registration_number = ranked.business_registration_number "
        "FROM ranked "
        "WHERE s.id = ranked.id AND ranked.row_number = 1"
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


def downgrade() -> None:
    op.drop_index(INDEX_NAME, table_name="stores")
    op.drop_column("stores", "business_registration_number")
