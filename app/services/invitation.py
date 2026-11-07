import secrets
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import NoReturn, Protocol
from uuid import UUID, uuid4

from sqlalchemy.exc import IntegrityError

from app.models.invitation import Invitation, InvitationAttempt
from app.models.membership import Membership
from app.models.store import Store
from app.models.user import User
from app.schemas.invitation import InvitationCreateRequest

INVITATION_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"
MAX_FAILED_ATTEMPTS = 5
LOCK_DURATION = timedelta(minutes=10)


class InvitationInvalidError(Exception):
    def __init__(self, remaining_attempts: int) -> None:
        self.remaining_attempts = remaining_attempts


class InvitationLockedError(Exception):
    def __init__(self, locked_until: datetime) -> None:
        self.locked_until = locked_until


class InvitationRevokedError(Exception):
    pass


class InvitationAlreadyJoinedError(Exception):
    def __init__(self, store_id: UUID, store_name: str) -> None:
        self.store_id = store_id
        self.store_name = store_name


class InvitationNotFoundError(Exception):
    pass


class InvitationCodeGenerationError(Exception):
    pass


class InvitationAlreadyAvailableError(Exception):
    def __init__(self, invitation: Invitation) -> None:
        self.invitation = invitation


@dataclass(frozen=True, slots=True)
class VerifiedInvitation:
    invitation: Invitation
    store: Store
    owner: User


class InvitationRepositoryProtocol(Protocol):
    async def create(self, invitation: Invitation) -> Invitation: ...

    async def get_context_by_code(
        self,
        code: str,
    ) -> tuple[Invitation, Store, User] | None: ...

    async def list_by_store_id(self, store_id: UUID) -> list[Invitation]: ...

    async def get_available_by_store_and_staff_name(
        self,
        store_id: UUID,
        staff_name: str,
    ) -> Invitation | None: ...

    async def get_by_id_and_store_id(
        self,
        invitation_id: UUID,
        store_id: UUID,
    ) -> Invitation | None: ...

    async def get_active_membership(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> Membership | None: ...

    async def get_membership(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> Membership | None: ...

    async def accept(
        self,
        invitation: Invitation,
        membership: Membership,
    ) -> Membership | None: ...

    async def save(self, invitation: Invitation) -> Invitation: ...

    async def get_attempt(self, user_id: UUID) -> InvitationAttempt | None: ...

    async def save_attempt(
        self,
        attempt: InvitationAttempt,
    ) -> InvitationAttempt: ...

    async def reset_attempt(self, user_id: UUID) -> None: ...


def generate_invitation_code() -> str:
    """혼동하기 쉬운 0/O/1/I를 제외한 6자리 코드를 만듭니다."""
    return "".join(secrets.choice(INVITATION_ALPHABET) for _ in range(6))


class InvitationService:
    def __init__(
        self,
        repository: InvitationRepositoryProtocol,
        *,
        code_generator: Callable[[], str] = generate_invitation_code,
    ) -> None:
        self._repository = repository
        self._code_generator = code_generator

    async def create(
        self,
        store: Store,
        creator_id: UUID,
        request: InvitationCreateRequest,
    ) -> Invitation:
        """소유자 매장에 사용할 일회용 초대 코드를 발급합니다."""
        store_id = store.id
        existing = await self._repository.get_available_by_store_and_staff_name(
            store_id,
            request.staff_name,
        )
        if existing is not None:
            raise InvitationAlreadyAvailableError(existing)

        for _ in range(10):
            invitation = Invitation(
                store_id=store_id,
                created_by_user_id=creator_id,
                code=self._code_generator(),
                staff_name=request.staff_name,
                hourly_wage=request.hourly_wage,
            )
            try:
                return await self._repository.create(invitation)
            except IntegrityError:
                existing = (
                    await self._repository.get_available_by_store_and_staff_name(
                        store_id,
                        request.staff_name,
                    )
                )
                if existing is not None:
                    raise InvitationAlreadyAvailableError(existing) from None
                continue
        raise InvitationCodeGenerationError

    async def list_for_store(self, store_id: UUID) -> list[Invitation]:
        """소유자 화면에 발급 이력을 최신순으로 반환합니다."""
        return await self._repository.list_by_store_id(store_id)

    async def get_shareable(
        self,
        store_id: UUID,
        invitation_id: UUID,
    ) -> Invitation:
        """공유할 수 있는 활성 초대 코드를 반환합니다."""
        invitation = await self._repository.get_by_id_and_store_id(
            invitation_id,
            store_id,
        )
        if invitation is None:
            raise InvitationNotFoundError
        if invitation.revoked_at is not None or invitation.accepted_at is not None:
            raise InvitationRevokedError
        return invitation

    async def verify(self, code: str, user_id: UUID) -> VerifiedInvitation:
        """코드 상태와 현재 사용자의 가입 가능 여부를 확인합니다."""
        now = datetime.now(UTC)
        attempt = await self._repository.get_attempt(user_id)
        if attempt is not None and attempt.locked_until is not None:
            if attempt.locked_until > now:
                raise InvitationLockedError(attempt.locked_until)
            await self._repository.reset_attempt(user_id)

        context = await self._repository.get_context_by_code(code)
        if context is None:
            await self._record_failure(user_id, now)

        invitation, store, owner = context
        membership = await self._repository.get_active_membership(
            store.id,
            user_id,
        )
        if store.owner_id == user_id or membership is not None:
            await self._repository.reset_attempt(user_id)
            raise InvitationAlreadyJoinedError(store.id, store.name)

        if (
            store.deleted_at is not None
            or invitation.revoked_at is not None
            or invitation.accepted_at is not None
        ):
            await self._repository.reset_attempt(user_id)
            raise InvitationRevokedError

        await self._repository.reset_attempt(user_id)
        return VerifiedInvitation(invitation, store, owner)

    async def join(self, code: str, user_id: UUID) -> tuple[Membership, Store]:
        """유효한 초대 코드를 사용해 직원 멤버십을 생성합니다."""
        verified = await self.verify(code, user_id)
        store = verified.store
        invitation = verified.invitation
        store_id = store.id
        store_name = store.name
        staff_name = invitation.staff_name
        hourly_wage = invitation.hourly_wage
        now = datetime.now(UTC)
        membership = await self._repository.get_membership(
            store_id,
            user_id,
        )
        if membership is None:
            membership = Membership(
                id=uuid4(),
                store_id=store_id,
                user_id=user_id,
                role="staff",
                staff_name=staff_name,
                hourly_wage=hourly_wage,
                joined_at=now,
            )
        else:
            membership.role = "staff"
            membership.staff_name = staff_name
            membership.hourly_wage = hourly_wage
            membership.joined_at = now
            membership.left_at = None
        try:
            saved = await self._repository.accept(
                invitation,
                membership,
            )
        except IntegrityError:
            existing = await self._repository.get_active_membership(
                store_id,
                user_id,
            )
            if existing is not None:
                raise InvitationAlreadyJoinedError(
                    store_id,
                    store_name,
                ) from None
            raise
        if saved is None:
            raise InvitationRevokedError
        return saved, store

    async def revoke(self, store_id: UUID, invitation_id: UUID) -> None:
        """소유자 매장의 초대 코드를 즉시 사용할 수 없게 합니다."""
        invitation = await self._repository.get_by_id_and_store_id(
            invitation_id,
            store_id,
        )
        if invitation is None:
            raise InvitationNotFoundError
        if invitation.revoked_at is not None or invitation.accepted_at is not None:
            raise InvitationRevokedError
        invitation.revoked_at = datetime.now(UTC)
        await self._repository.save(invitation)

    async def _record_failure(self, user_id: UUID, now: datetime) -> NoReturn:
        attempt = await self._repository.get_attempt(user_id)
        if attempt is None:
            attempt = InvitationAttempt(user_id=user_id, failure_count=0)
        if attempt.locked_until is not None and attempt.locked_until <= now:
            attempt.failure_count = 0
            attempt.locked_until = None

        attempt.failure_count += 1
        if attempt.failure_count >= MAX_FAILED_ATTEMPTS:
            attempt.locked_until = now + LOCK_DURATION
            await self._repository.save_attempt(attempt)
            raise InvitationLockedError(attempt.locked_until)

        await self._repository.save_attempt(attempt)
        raise InvitationInvalidError(MAX_FAILED_ATTEMPTS - attempt.failure_count)
