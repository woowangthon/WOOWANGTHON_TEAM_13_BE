from collections.abc import Iterator
from datetime import UTC, datetime, time
from typing import Any, cast
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.models.invitation import Invitation, InvitationScheduleAssignment
from app.models.membership import Membership
from app.models.schedule import ScheduleAssignment, ShiftTemplate
from app.models.store import Store
from app.models.user import User
from app.repositories.invitation import InvitationRepository


class SyncSessionAdapter:
    """실제 SQL을 SQLite에서 실행하도록 동기 세션을 감쌉니다."""

    def __init__(self, session: Session) -> None:
        self._session = session

    async def execute(self, query: Any) -> Any:
        return self._session.execute(query)

    def add(self, item: Any) -> None:
        self._session.add(item)

    def add_all(self, items: list[Any]) -> None:
        self._session.add_all(items)

    async def commit(self) -> None:
        self._session.commit()

    async def rollback(self) -> None:
        self._session.rollback()

    async def refresh(self, item: Any) -> None:
        self._session.refresh(item)


@pytest.fixture
def session() -> Iterator[Session]:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    tables = [
        User.__table__,
        Store.__table__,
        ShiftTemplate.__table__,
        Invitation.__table__,
        InvitationScheduleAssignment.__table__,
        Membership.__table__,
        ScheduleAssignment.__table__,
    ]
    User.metadata.create_all(engine, tables=tables)
    with Session(engine, expire_on_commit=False) as db_session:
        yield db_session
    engine.dispose()


@pytest.mark.asyncio
async def test_accept_moves_invitation_schedule_to_fixed_schedule(
    session: Session,
) -> None:
    owner = User(
        id=uuid4(),
        auth_user_id=uuid4(),
        nickname="사장님",
        provider="kakao",
    )
    staff = User(
        id=uuid4(),
        auth_user_id=uuid4(),
        nickname="직원",
        provider="kakao",
    )
    store = Store(
        id=uuid4(),
        owner_id=owner.id,
        name="매장",
        address="주소",
    )
    old_template = ShiftTemplate(
        id=uuid4(),
        store_id=store.id,
        name="기존",
        start_time=time(9),
        end_time=time(12),
    )
    invited_template = ShiftTemplate(
        id=uuid4(),
        store_id=store.id,
        name="초대 근무",
        start_time=time(12),
        end_time=time(18),
    )
    invitation = Invitation(
        id=uuid4(),
        store_id=store.id,
        created_by_user_id=owner.id,
        code="K7P2QX",
        staff_name="지은",
        hourly_wage=10_320,
        schedule=[
            InvitationScheduleAssignment(
                template_id=invited_template.id,
                weekday=3,
            )
        ],
    )
    session.add_all([owner, staff, store, old_template, invited_template, invitation])
    session.add(
        ScheduleAssignment(
            store_id=store.id,
            template_id=old_template.id,
            weekday=1,
            assignee_user_id=staff.id,
        )
    )
    session.commit()

    repository = InvitationRepository(
        cast(AsyncSession, SyncSessionAdapter(session))
    )
    context = await repository.get_context_by_code("K7P2QX")
    assert context is not None
    membership = Membership(
        id=uuid4(),
        store_id=store.id,
        user_id=staff.id,
        role="staff",
        staff_name="지은",
        hourly_wage=10_320,
        tax_type="none",
        joined_at=datetime.now(UTC),
    )

    saved = await repository.accept(context[0], membership)

    assignments = session.scalars(
        select(ScheduleAssignment).where(
            ScheduleAssignment.store_id == store.id,
            ScheduleAssignment.assignee_user_id == staff.id,
            ScheduleAssignment.effective_until.is_(None),
        )
    ).all()
    accepted_by_user_id = session.scalar(
        select(Invitation.accepted_by_user_id).where(Invitation.id == invitation.id)
    )
    assert saved is not None
    assert [(item.template_id, item.weekday) for item in assignments] == [
        (invited_template.id, 3)
    ]
    assert accepted_by_user_id == staff.id
