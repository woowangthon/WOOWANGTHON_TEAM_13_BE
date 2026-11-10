from collections.abc import Sequence
from typing import Any, Protocol
from urllib.parse import quote

import httpx


class StorageError(Exception):
    """파일 저장소 호출이 실패했을 때 발생합니다."""


class FileStorage(Protocol):
    async def upload(self, path: str, data: bytes, content_type: str) -> None: ...

    async def delete(self, paths: Sequence[str]) -> None: ...

    async def signed_urls(
        self,
        paths: Sequence[str],
        expires_in_seconds: int,
    ) -> dict[str, str]: ...


class SupabaseStorageClient:
    def __init__(
        self,
        *,
        supabase_url: str,
        secret_key: str,
        bucket: str,
        timeout_seconds: float = 20,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        """Supabase Storage 호출에 필요한 주소, 서버 키, 버킷을 받습니다."""
        self._base_url = supabase_url.rstrip("/") + "/storage/v1"
        self._secret_key = secret_key
        self._bucket = bucket
        self._timeout_seconds = timeout_seconds
        self._transport = transport

    def _headers(self) -> dict[str, str]:
        """서버 키 인증 헤더를 만듭니다."""
        return {
            "apikey": self._secret_key,
            "Authorization": f"Bearer {self._secret_key}",
        }

    async def _request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Storage API를 호출하고 실패하면 StorageError로 바꿉니다."""
        if not self._secret_key:
            raise StorageError("Supabase secret key is not configured")
        headers = {**self._headers(), **kwargs.pop("headers", {})}
        try:
            async with httpx.AsyncClient(
                timeout=self._timeout_seconds,
                transport=self._transport,
            ) as client:
                response = await client.request(
                    method,
                    self._base_url + path,
                    headers=headers,
                    **kwargs,
                )
                response.raise_for_status()
                return response
        except httpx.HTTPError as exc:
            raise StorageError(f"Storage request failed: {method} {path}") from exc

    async def upload(self, path: str, data: bytes, content_type: str) -> None:
        """파일을 버킷에 올립니다. 같은 경로가 있으면 덮어씁니다."""
        await self._request(
            "POST",
            f"/object/{self._bucket}/{quote(path)}",
            content=data,
            headers={"Content-Type": content_type, "x-upsert": "true"},
        )

    def public_url(self, path: str) -> str:
        """공개 버킷 파일의 만료되지 않는 주소를 만듭니다."""
        return f"{self._base_url}/object/public/{self._bucket}/{quote(path)}"

    async def delete(self, paths: Sequence[str]) -> None:
        """버킷에서 파일을 지웁니다."""
        if not paths:
            return
        await self._request(
            "DELETE",
            f"/object/{self._bucket}",
            json={"prefixes": list(paths)},
        )

    async def signed_urls(
        self,
        paths: Sequence[str],
        expires_in_seconds: int,
    ) -> dict[str, str]:
        """여러 파일의 시간 제한 주소를 한 번에 발급합니다."""
        unique = list(dict.fromkeys(paths))
        if not unique:
            return {}
        response = await self._request(
            "POST",
            f"/object/sign/{self._bucket}",
            json={"expiresIn": expires_in_seconds, "paths": unique},
        )
        try:
            items = response.json()
        except ValueError as exc:
            raise StorageError("Storage returned invalid JSON") from exc
        if not isinstance(items, list):
            raise StorageError("Storage returned an unexpected response")
        urls: dict[str, str] = {}
        for item in items:
            if not isinstance(item, dict):
                continue
            path = item.get("path")
            signed = item.get("signedURL")
            if (
                isinstance(path, str)
                and isinstance(signed, str)
                and not item.get("error")
            ):
                urls[path] = self._base_url + signed
        return urls
