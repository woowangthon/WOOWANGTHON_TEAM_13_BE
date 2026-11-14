from datetime import UTC, datetime, time
from typing import Any, Protocol
from uuid import UUID

from sqlalchemy.exc import IntegrityError

from app.models.business_verification import BusinessVerification
from app.models.schedule import ShiftTemplate
from app.models.store import Store
from app.schemas.store import StoreCreateRequest, StoreUpdateRequest
from app.services.business_verification import VERIFIED_STATUS


class StoreNotFoundError(Exception):
    """소유자가 접근할 수 있는 매장을 찾지 못했을 때 발생합니다."""


class BusinessVerificationRequiredError(Exception):
    """유효한 본인 소유 사업자 인증 결과가 필요합니다."""


class BusinessRegistrationNumberAlreadyUsedError(Exception):
    """이미 활성 매장에 사용 중인 사업자등록번호입니다."""


class StoreRepositoryProtocol(Protocol):
    async def create(self, store: Store) -> Store: ...

    async def exists_active_by_business_registration_number(
        self,
        business_registration_number: str,
        *,
        exclude_store_id: UUID | None = None,
    ) -> bool: ...

    async def list_by_owner_id(self, owner_id: UUID) -> list[Store]: ...

    async def get_by_id_and_owner_id(
        self,
        store_id: UUID,
        owner_id: UUID,
    ) -> Store | None: ...

    async def save(self, store: Store) -> Store: ...


class BusinessVerificationRepositoryProtocol(Protocol):
    async def get_by_id_and_requester_id(
        self,
        verification_id: int,
        requester_id: UUID,
    ) -> BusinessVerification | None: ...


class StoreService:
    def __init__(
        self,
        repository: StoreRepositoryProtocol,
        business_verification_repository: (BusinessVerificationRepositoryProtocol),
    ) -> None:
        """매장 비즈니스 로직에 사용할 저장소를 받습니다."""
        self._repository = repository
        self._business_verification_repository = business_verification_repository

    async def create(
        self,
        owner_id: UUID,
        request: StoreCreateRequest,
    ) -> Store:
        """로그인한 사용자의 매장을 생성합니다."""
        verification = await self._get_verified_business(
            request.business_verification_id,
            owner_id,
        )
        await self._require_unused_business_registration_number(
            verification.business_registration_number,
        )
        store = Store(
            owner_id=owner_id,
            name=request.name,
            address=request.address,
            business_verification_id=request.business_verification_id,
            business_registration_number=(
                verification.business_registration_number
            ),
            photo_url=request.photo_url,
            payday=request.payday,
            business_size=request.business_size,
            closed_weekdays=request.closed_weekdays,
            closed_on_holidays=request.closed_on_holidays,
            shift_templates=[
                ShiftTemplate(
                    name=item.name,
                    start_time=self._parse_time(item.start),
                    end_time=self._parse_time(item.end),
                    role=item.role,
                    headcount=item.headcount,
                    sort_order=item.sort_order,
                )
                for item in request.shift_templates
            ],
        )
        try:
            return await self._repository.create(store)
        except IntegrityError:
            await self._raise_if_business_registration_number_is_used(
                verification.business_registration_number,
            )
            raise

    @staticmethod
    def _parse_time(value: str) -> time:
        hour, minute = (int(part) for part in value.split(":"))
        return time(hour, minute)

    async def list_for_owner(self, owner_id: UUID) -> list[Store]:
        """로그인한 사용자가 소유한 매장 목록을 조회합니다."""
        return await self._repository.list_by_owner_id(owner_id)

    async def get_for_owner(self, store_id: UUID, owner_id: UUID) -> Store:
        """로그인한 사용자가 소유한 매장 상세 정보를 조회합니다."""
        store = await self._repository.get_by_id_and_owner_id(
            store_id,
            owner_id,
        )
        if store is None:
            raise StoreNotFoundError
        return store

    async def update(
        self,
        store_id: UUID,
        owner_id: UUID,
        request: StoreUpdateRequest,
    ) -> Store:
        """로그인한 사용자가 소유한 매장 정보를 수정합니다."""
        store = await self.get_for_owner(store_id, owner_id)
        fields: dict[str, Any] = request.model_dump(
            exclude_unset=True,
            by_alias=False,
        )
        business_verification_id = fields.get("business_verification_id")
        if isinstance(business_verification_id, int):
            verification = await self._get_verified_business(
                business_verification_id,
                owner_id,
            )
            await self._require_unused_business_registration_number(
                verification.business_registration_number,
                exclude_store_id=store_id,
            )
            fields["business_registration_number"] = (
                verification.business_registration_number
            )
        for field, value in fields.items():
            setattr(store, field, value)
        try:
            return await self._repository.save(store)
        except IntegrityError:
            if isinstance(business_verification_id, int):
                await self._raise_if_business_registration_number_is_used(
                    fields["business_registration_number"],
                    exclude_store_id=store_id,
                )
            raise

    async def delete(self, store_id: UUID, owner_id: UUID) -> None:
        """로그인한 사용자가 소유한 매장을 삭제 처리합니다."""
        store = await self.get_for_owner(store_id, owner_id)
        store.deleted_at = datetime.now(UTC)
        await self._repository.save(store)

    async def _get_verified_business(
        self,
        verification_id: int,
        owner_id: UUID,
    ) -> BusinessVerification:
        verification = (
            await self._business_verification_repository.get_by_id_and_requester_id(
                verification_id,
                owner_id,
            )
        )
        if verification is None or verification.status != VERIFIED_STATUS:
            raise BusinessVerificationRequiredError
        return verification

    async def _require_unused_business_registration_number(
        self,
        business_registration_number: str,
        *,
        exclude_store_id: UUID | None = None,
    ) -> None:
        if await self._repository.exists_active_by_business_registration_number(
            business_registration_number,
            exclude_store_id=exclude_store_id,
        ):
            raise BusinessRegistrationNumberAlreadyUsedError

    async def _raise_if_business_registration_number_is_used(
        self,
        business_registration_number: str,
        *,
        exclude_store_id: UUID | None = None,
    ) -> None:
        """동시 생성 경합의 DB 유니크 오류를 도메인 오류로 바꿉니다."""
        await self._require_unused_business_registration_number(
            business_registration_number,
            exclude_store_id=exclude_store_id,
        )
