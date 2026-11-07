from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.models.invitation import Invitation, InvitationAttempt
from app.models.membership import Membership
from app.models.store import Store
from app.models.user import User
from app.schemas.invitation import InvitationCreateRequest
from app.services.invitation import (
    INVITATION_ALPHABET,
    InvitationAlreadyAvailableError,
    InvitationAlreadyJoinedError,
    InvitationInvalidError,
    InvitationLockedError,
    InvitationRevokedError,
    InvitationService,
    generate_invitation_code,
)


class FakeInvitationRepository:
    def __init__(
        self,
        context: tuple[Invitation, Store, User] | None = None,
    ) -> None:
        self.context = context
        self.membership: Membership | None = None
        self.attempts: dict[UUID, InvitationAttempt] = {}
        self.created: list[Invitation] = []
        self.consume_succeeds = True

    async def create(self, invitation: Invitation) -> Invitation:
        invitation.id = uuid4()
        invitation.created_at = datetime.now(UTC)
        self.created.append(invitation)
        return invitation

    async def get_context_by_code(
        self,
        code: str,
    ) -> tuple[Invitation, Store, User] | None:
        if self.context is None or self.context[0].code != code:
            return None
        return self.context

    async def list_by_store_id(self, store_id: UUID) -> list[Invitation]:
        invitations = list(self.created)
        if self.context is not None:
            invitations.append(self.context[0])
        return [item for item in invitations if item.store_id == store_id]

    async def get_available_by_store_and_staff_name(
        self,
        store_id: UUID,
        staff_name: str,
    ) -> Invitation | None:
        for invitation in await self.list_by_store_id(store_id):
            if (
                invitation.staff_name == staff_name
                and invitation.revoked_at is None
                and invitation.accepted_at is None
            ):
                return invitation
        return None

    async def get_by_id_and_store_id(
        self,
        invitation_id: UUID,
        store_id: UUID,
    ) -> Invitation | None:
        if self.context is None:
            return None
        invitation = self.context[0]
        if invitation.id == invitation_id and invitation.store_id == store_id:
            return invitation
        return None

    async def get_active_membership(
        self,
        store_id: UUID,
        user_id: UUID,
    ) -> Membership | None:
        if (
            self.membership is not None
            and self.membership.store_id == store_id
            and self.membership.user_id == user_id
            and self.membership.left_at is None
        ):
            return self.membership
        return None

    async def accept(
        self,
        invitation: Invitation,
        membership: Membership,
    ) -> Membership | None:
        if not self.consume_succeeds:
            return None
        invitation.accepted_at = membership.joined_at
        invitation.accepted_by_user_id = membership.user_id
        self.membership = membership
        return membership

    async def save(self, invitation: Invitation) -> Invitation:
        return invitation

    async def get_attempt(self, user_id: UUID) -> InvitationAttempt | None:
        return self.attempts.get(user_id)

    async def save_attempt(
        self,
        attempt: InvitationAttempt,
    ) -> InvitationAttempt:
        self.attempts[attempt.user_id] = attempt
        return attempt

    async def reset_attempt(self, user_id: UUID) -> None:
        self.attempts.pop(user_id, None)


def make_context() -> tuple[Invitation, Store, User]:
    owner = User(
        id=uuid4(),
        auth_user_id=uuid4(),
        nickname="박 사장님",
        email=None,
        provider="kakao",
    )
    store = Store(
        id=uuid4(),
        owner_id=owner.id,
        name="달빛 카페",
        address="서울시 마포구",
        photo_url=None,
    )
    invitation = Invitation(
        id=uuid4(),
        store_id=store.id,
        created_by_user_id=owner.id,
        code="K7P2QX",
        staff_name="지은",
        hourly_wage=10_320,
        created_at=datetime.now(UTC),
    )
    return invitation, store, owner


def test_generated_code_is_six_unambiguous_characters() -> None:
    for _ in range(20):
        code = generate_invitation_code()

        assert len(code) == 6
        assert set(code) <= set(INVITATION_ALPHABET)
        assert not set(code) & set("0O1I")


@pytest.mark.asyncio
async def test_create_copies_staff_terms_to_invitation() -> None:
    _, store, owner = make_context()
    repository = FakeInvitationRepository()
    service = InvitationService(repository, code_generator=lambda: "K7P2QX")

    invitation = await service.create(
        store,
        owner.id,
        InvitationCreateRequest(staffName=" 지은 ", hourlyWage=10_320),
    )

    assert invitation.code == "K7P2QX"
    assert invitation.staff_name == "지은"
    assert invitation.hourly_wage == 10_320
    assert invitation.store_id == store.id


@pytest.mark.asyncio
async def test_create_rejects_duplicate_available_invitation() -> None:
    _, store, owner = make_context()
    repository = FakeInvitationRepository()
    service = InvitationService(repository, code_generator=lambda: "K7P2QX")
    request = InvitationCreateRequest(staffName="지은", hourlyWage=10_320)
    await service.create(store, owner.id, request)

    with pytest.raises(InvitationAlreadyAvailableError):
        await service.create(store, owner.id, request)


@pytest.mark.asyncio
async def test_five_invalid_codes_lock_user_for_ten_minutes() -> None:
    repository = FakeInvitationRepository()
    service = InvitationService(repository)
    user_id = uuid4()

    for remaining in (4, 3, 2, 1):
        with pytest.raises(InvitationInvalidError) as exc_info:
            await service.verify("ZZZZZZ", user_id)
        assert exc_info.value.remaining_attempts == remaining

    before = datetime.now(UTC)
    with pytest.raises(InvitationLockedError) as exc_info:
        await service.verify("ZZZZZZ", user_id)

    assert exc_info.value.locked_until > before
    with pytest.raises(InvitationLockedError):
        await service.verify("K7P2QX", user_id)


@pytest.mark.asyncio
async def test_verify_rejects_existing_membership_with_store_detail() -> None:
    context = make_context()
    repository = FakeInvitationRepository(context)
    user_id = uuid4()
    repository.membership = Membership(
        id=uuid4(),
        store_id=context[1].id,
        user_id=user_id,
        role="staff",
        staff_name="지은",
        hourly_wage=10_320,
        joined_at=datetime.now(UTC),
    )

    with pytest.raises(InvitationAlreadyJoinedError) as exc_info:
        await InvitationService(repository).verify("K7P2QX", user_id)

    assert exc_info.value.store_id == context[1].id
    assert exc_info.value.store_name == "달빛 카페"


@pytest.mark.asyncio
async def test_join_creates_membership_and_consumes_invitation() -> None:
    context = make_context()
    repository = FakeInvitationRepository(context)
    user_id = uuid4()

    membership, store = await InvitationService(repository).join(
        "K7P2QX",
        user_id,
    )

    assert store is context[1]
    assert membership.user_id == user_id
    assert membership.staff_name == "지은"
    assert membership.hourly_wage == 10_320
    assert context[0].accepted_by_user_id == user_id
    assert context[0].accepted_at is not None


@pytest.mark.asyncio
async def test_join_rejects_invitation_consumed_by_concurrent_request() -> None:
    context = make_context()
    repository = FakeInvitationRepository(context)
    repository.consume_succeeds = False

    with pytest.raises(InvitationRevokedError):
        await InvitationService(repository).join("K7P2QX", uuid4())


@pytest.mark.asyncio
async def test_revoked_invitation_cannot_be_verified() -> None:
    context = make_context()
    context[0].revoked_at = datetime.now(UTC)

    with pytest.raises(InvitationRevokedError):
        await InvitationService(FakeInvitationRepository(context)).verify(
            "K7P2QX",
            uuid4(),
        )


@pytest.mark.asyncio
async def test_used_invitation_cannot_be_revoked() -> None:
    context = make_context()
    context[0].accepted_at = datetime.now(UTC)
    context[0].accepted_by_user_id = uuid4()

    with pytest.raises(InvitationRevokedError):
        await InvitationService(FakeInvitationRepository(context)).revoke(
            context[1].id,
            context[0].id,
        )
