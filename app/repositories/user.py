from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.user import User


class UserRepository:
    def __init__(self, session: AsyncSession) -> None:
        """사용자 데이터 접근에 사용할 DB 세션을 받습니다."""
        self._session = session

    async def get_by_auth_user_id(
        self,
        auth_user_id: UUID,
        *,
        include_deleted: bool = False,
    ) -> User | None:
        """Supabase 사용자 ID로 서비스 사용자를 조회합니다."""
        query = select(User).where(User.auth_user_id == auth_user_id)
        if not include_deleted:
            query = query.where(User.deleted_at.is_(None))
        result = await self._session.execute(query)
        return result.scalar_one_or_none()

    async def create(self, user: User) -> User:
        """새 사용자를 저장합니다."""
        self._session.add(user)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(user)
        return user

    async def save(self, user: User) -> User:
        """변경된 사용자 정보를 저장합니다."""
        self._session.add(user)
        try:
            await self._session.commit()
        except SQLAlchemyError:
            await self._session.rollback()
            raise
        await self._session.refresh(user)
        return user
