from collections.abc import Iterator
from datetime import UTC, date, datetime
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.business_verification import BusinessVerification
from app.models.store import Store
from app.models.user import User
from app.repositories.store import StoreRepository


class SyncSessionAdapter:
    """실제 StoreRepository 쿼리를 SQLite에서 실행합니다."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def scalar(self, query: Any) -> Any:
        return self._session.scalar(query)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    tables = [
        User.__table__,
        BusinessVerification.__table__,
        Store.__table__,
    ]
    User.metadata.create_all(engine, tables=tables)
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session
    engine.dispose()


def make_owner(session: Session) -> User:
    owner = User(
        id=uuid4(),
        auth_user_id=uuid4(),
        nickname="사장님",
        provider="kakao",
    )
    session.add(owner)
    return owner


def make_verification(
    owner: User,
    *,
    verification_id: int,
    business_registration_number: str = "1234567890",
) -> BusinessVerification:
    return BusinessVerification(
        id=verification_id,
        requester_id=owner.id,
        business_registration_number=business_registration_number,
        owner_name=None,
        business_start_date=date(2026, 1, 1),
        status="VERIFIED",
        provider_message="확인",
    )


@pytest.mark.asyncio
async def test_exists_finds_legacy_store_through_verification(
    session: Session,
) -> None:
    owner = make_owner(session)
    verification = make_verification(owner, verification_id=1)
    store = Store(
        id=uuid4(),
        owner_id=owner.id,
        name="기존 매장",
        address="서울",
        business_verification_id=verification.id,
        business_registration_number=None,
    )
    session.add_all([verification, store])
    session.commit()
    repository = StoreRepository(cast(AsyncSession, SyncSessionAdapter(session)))

    assert await repository.exists_active_by_business_registration_number(
        "1234567890"
    )
    assert not await repository.exists_active_by_business_registration_number(
        "1234567890",
        exclude_store_id=store.id,
    )


def test_unique_index_allows_deleted_store_but_rejects_two_active(
    session: Session,
) -> None:
    owner = make_owner(session)
    verification1 = make_verification(owner, verification_id=1)
    verification2 = make_verification(owner, verification_id=2)
    deleted = Store(
        id=uuid4(),
        owner_id=owner.id,
        name="삭제 매장",
        address="서울",
        business_verification_id=verification1.id,
        business_registration_number="1234567890",
        deleted_at=datetime.now(UTC),
    )
    active = Store(
        id=uuid4(),
        owner_id=owner.id,
        name="활성 매장",
        address="부산",
        business_verification_id=verification2.id,
        business_registration_number="1234567890",
    )
    session.add_all([verification1, verification2, deleted, active])
    session.commit()

    duplicate = Store(
        id=uuid4(),
        owner_id=owner.id,
        name="중복 매장",
        address="대전",
        business_verification_id=verification2.id,
        business_registration_number="1234567890",
    )
    session.add(duplicate)

    with pytest.raises(IntegrityError):
        session.commit()
