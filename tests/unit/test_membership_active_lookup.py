from collections.abc import Iterator
from datetime import UTC, datetime
from typing import Any, cast
from uuid import UUID, uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.membership import Membership
from app.models.store import Store
from app.models.user import User
from app.repositories.membership import MembershipRepository

NOW = datetime(2026, 11, 7, tzinfo=UTC)


class SyncSessionAdapter:
    """실제 쿼리를 SQLite에서 실행하도록 동기 세션을 감쌉니다."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, query: Any) -> Any:
        return self._session.execute(query)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    tables = [User.__table__, Store.__table__, Membership.__table__]
    User.metadata.create_all(engine, tables=tables)
    with Session(engine) as db_session:
        yield db_session
    engine.dispose()


def repository(session: Session) -> MembershipRepository:
    return MembershipRepository(cast(AsyncSession, SyncSessionAdapter(session)))


def add_membership(
    session: Session,
    *,
    left_at: datetime | None = None,
    store_deleted_at: datetime | None = None,
) -> tuple[UUID, UUID]:
    store_id = uuid4()
    user_id = uuid4()
    session.add(
        Store(
            id=store_id,
            owner_id=uuid4(),
            name="매장",
            address="주소",
            deleted_at=store_deleted_at,
        )
    )
    session.add(
        Membership(
            store_id=store_id,
            user_id=user_id,
            role="staff",
            staff_name="민지",
            hourly_wage=10320,
            joined_at=NOW,
            left_at=left_at,
        )
    )
    session.commit()
    return store_id, user_id


async def test_finds_active_member(session: Session) -> None:
    store_id, user_id = add_membership(session)

    found = await repository(session).get_active_by_store_and_user_id(
        store_id,
        user_id,
    )

    assert found is not None
    assert found.user_id == user_id


async def test_excludes_member_who_left(session: Session) -> None:
    store_id, user_id = add_membership(session, left_at=NOW)

    found = await repository(session).get_active_by_store_and_user_id(
        store_id,
        user_id,
    )

    assert found is None


async def test_excludes_member_of_deleted_store(session: Session) -> None:
    store_id, user_id = add_membership(session, store_deleted_at=NOW)

    found = await repository(session).get_active_by_store_and_user_id(
        store_id,
        user_id,
    )

    assert found is None


async def test_does_not_match_another_store(session: Session) -> None:
    _, user_id = add_membership(session)
    other_store_id, _ = add_membership(session)

    found = await repository(session).get_active_by_store_and_user_id(
        other_store_id,
        user_id,
    )

    assert found is None
