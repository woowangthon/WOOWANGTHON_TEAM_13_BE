from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol
from uuid import UUID

from app.models.manual import Manual, ManualCategory
from app.schemas.manual import (
    ManualCategoryCreateRequest,
    ManualCreateRequest,
    ManualUpdateRequest,
)
from app.services.store_access import StoreAccessProtocol


class ManualNotFoundError(Exception):
    """매장에서 매뉴얼을 찾지 못했을 때 발생합니다."""


class ManualCategoryNotFoundError(Exception):
    """매장에서 매뉴얼 카테고리를 찾지 못했을 때 발생합니다."""


@dataclass(frozen=True, slots=True)
class ManualTemplate:
    """사장님에게 추천하는 고정 매뉴얼 템플릿입니다."""

    icon: str
    title: str
    body: str
    keywords: tuple[str, ...]


MANUAL_TEMPLATES: tuple[ManualTemplate, ...] = (
    ManualTemplate(
        icon="open",
        title="오픈 순서",
        body="출근 후 오픈 준비 순서를 차례대로 적어 주세요.",
        keywords=("오픈", "출근", "준비"),
    ),
    ManualTemplate(
        icon="close",
        title="마감 순서",
        body="마감 청소와 정산, 퇴근 전 확인 사항을 적어 주세요.",
        keywords=("마감", "청소", "정산", "퇴근"),
    ),
    ManualTemplate(
        icon="refund",
        title="환불·교환",
        body="환불과 교환이 가능한 경우와 처리 방법을 적어 주세요.",
        keywords=("환불", "교환", "고객 응대", "결제"),
    ),
    ManualTemplate(
        icon="delivery",
        title="배달 주문",
        body="배달 주문 접수와 포장, 전달 방법을 적어 주세요.",
        keywords=("배달", "포장", "주문"),
    ),
    ManualTemplate(
        icon="wifi",
        title="와이파이",
        body="손님에게 안내할 와이파이 이름과 비밀번호를 적어 주세요.",
        keywords=("와이파이", "인터넷", "고객 응대"),
    ),
    ManualTemplate(
        icon="restroom",
        title="화장실",
        body="화장실 위치와 비밀번호, 청소 주기를 적어 주세요.",
        keywords=("화장실", "청소", "고객 응대"),
    ),
)


class ManualRepositoryProtocol(Protocol):
    async def create_category(self, category: ManualCategory) -> ManualCategory: ...

    async def get_category(
        self,
        category_id: UUID,
        store_id: UUID,
    ) -> ManualCategory | None: ...

    async def create(self, manual: Manual) -> Manual: ...

    async def list_by_store_id(self, store_id: UUID) -> list[Manual]: ...

    async def get_by_id_and_store_id(
        self,
        manual_id: UUID,
        store_id: UUID,
    ) -> Manual | None: ...

    async def save(self, manual: Manual) -> Manual: ...


class ManualService:
    def __init__(
        self,
        repository: ManualRepositoryProtocol,
        store_access: StoreAccessProtocol,
    ) -> None:
        """매뉴얼 비즈니스 로직에 사용할 저장소와 권한 검사기를 받습니다."""
        self._repository = repository
        self._store_access = store_access

    async def _ensure_category(self, category_id: UUID, store_id: UUID) -> None:
        """카테고리가 같은 매장에 속하는지 검사합니다."""
        category = await self._repository.get_category(category_id, store_id)
        if category is None:
            raise ManualCategoryNotFoundError

    async def _get_manual(self, store_id: UUID, manual_id: UUID) -> Manual:
        """매장의 매뉴얼을 조회하고 없으면 예외를 발생시킵니다."""
        manual = await self._repository.get_by_id_and_store_id(manual_id, store_id)
        if manual is None:
            raise ManualNotFoundError
        return manual

    async def create_category(
        self,
        store_id: UUID,
        user_id: UUID,
        request: ManualCategoryCreateRequest,
    ) -> ManualCategory:
        """매장의 매뉴얼 카테고리를 생성합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        category = ManualCategory(store_id=store_id, name=request.name)
        return await self._repository.create_category(category)

    async def recommend(
        self,
        store_id: UUID,
        user_id: UUID,
        keywords: list[str],
    ) -> list[ManualTemplate]:
        """키워드와 맞는 템플릿을 앞에 두어 고정 템플릿을 추천합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        wanted = {keyword.strip() for keyword in keywords if keyword.strip()}
        return sorted(
            MANUAL_TEMPLATES,
            key=lambda template: not wanted.intersection(template.keywords),
        )

    async def create(
        self,
        store_id: UUID,
        user_id: UUID,
        request: ManualCreateRequest,
    ) -> Manual:
        """매장의 매뉴얼을 등록합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        if request.category_id is not None:
            await self._ensure_category(request.category_id, store_id)
        manual = Manual(
            store_id=store_id,
            category_id=request.category_id,
            icon=request.icon,
            title=request.title,
            body=request.body,
        )
        return await self._repository.create(manual)

    async def list_for_store(self, store_id: UUID, user_id: UUID) -> list[Manual]:
        """매장의 매뉴얼 목록을 조회합니다."""
        await self._store_access.ensure_member(store_id, user_id)
        return await self._repository.list_by_store_id(store_id)

    async def get(self, store_id: UUID, manual_id: UUID, user_id: UUID) -> Manual:
        """매장의 매뉴얼 상세 정보를 조회합니다."""
        await self._store_access.ensure_member(store_id, user_id)
        return await self._get_manual(store_id, manual_id)

    async def update(
        self,
        store_id: UUID,
        manual_id: UUID,
        user_id: UUID,
        request: ManualUpdateRequest,
    ) -> Manual:
        """매장의 매뉴얼을 수정합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        manual = await self._get_manual(store_id, manual_id)
        fields: Mapping[str, Any] = request.model_dump(
            exclude_unset=True,
            by_alias=False,
        )
        category_id = fields.get("category_id")
        if category_id is not None:
            await self._ensure_category(category_id, store_id)
        for field, value in fields.items():
            setattr(manual, field, value)
        return await self._repository.save(manual)

    async def delete(self, store_id: UUID, manual_id: UUID, user_id: UUID) -> None:
        """매장의 매뉴얼을 삭제 처리합니다."""
        await self._store_access.ensure_owner(store_id, user_id)
        manual = await self._get_manual(store_id, manual_id)
        manual.deleted_at = datetime.now(UTC)
        await self._repository.save(manual)
