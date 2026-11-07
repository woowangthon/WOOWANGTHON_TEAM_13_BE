from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, MagicMock
from uuid import uuid4

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.membership import Membership
from app.repositories.membership import MembershipRepository


@pytest.mark.asyncio
async def test_leave_does_not_revoke_invitation_by_staff_name() -> None:
    session = MagicMock(spec=AsyncSession)
    session.commit = AsyncMock()
    session.rollback = AsyncMock()
    session.refresh = AsyncMock()
    repository = MembershipRepository(cast(AsyncSession, session))
    membership = Membership(
        id=uuid4(),
        store_id=uuid4(),
        user_id=uuid4(),
        role="staff",
        staff_name="동명이인",
        hourly_wage=10_320,
        joined_at=datetime.now(UTC),
    )
    left_at = datetime.now(UTC)

    result = await repository.leave(membership, left_at)

    assert result.left_at == left_at
    session.execute.assert_not_awaited()
    session.commit.assert_awaited_once()
    session.refresh.assert_awaited_once_with(membership)
