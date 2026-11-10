import json

import httpx
import pytest

from app.integrations.storage import StorageError, SupabaseStorageClient

BASE = "https://project.supabase.co"


def make_client(
    handler: httpx.MockTransport,
    secret_key: str = "sb_secret_test",
) -> SupabaseStorageClient:
    return SupabaseStorageClient(
        supabase_url=BASE + "/",
        secret_key=secret_key,
        bucket="content-files",
        transport=handler,
    )


async def test_upload_sends_file_with_server_key() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"Key": "content-files/a/b.jpg"})

    client = make_client(httpx.MockTransport(handle))
    await client.upload("stores/s/recipes/r/menu-1.jpg", b"jpeg", "image/jpeg")

    [request] = seen
    assert request.method == "POST"
    assert str(request.url) == (
        BASE + "/storage/v1/object/content-files/stores/s/recipes/r/menu-1.jpg"
    )
    assert request.headers["apikey"] == "sb_secret_test"
    assert request.headers["Content-Type"] == "image/jpeg"
    assert request.headers["x-upsert"] == "true"
    assert request.content == b"jpeg"


async def test_signed_urls_builds_full_urls_and_skips_errors() -> None:
    def handle(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        assert request.url.path == "/storage/v1/object/sign/content-files"
        assert body == {"expiresIn": 60, "paths": ["a.jpg", "missing.jpg"]}
        return httpx.Response(
            200,
            json=[
                {
                    "path": "a.jpg",
                    "signedURL": "/object/sign/content-files/a.jpg?token=t",
                    "error": None,
                },
                {"path": "missing.jpg", "signedURL": None, "error": "not found"},
            ],
        )

    client = make_client(httpx.MockTransport(handle))
    urls = await client.signed_urls(["a.jpg", "missing.jpg", "a.jpg"], 60)

    assert urls == {
        "a.jpg": BASE + "/storage/v1/object/sign/content-files/a.jpg?token=t"
    }


async def test_delete_sends_prefixes() -> None:
    seen: list[httpx.Request] = []

    def handle(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=[])

    client = make_client(httpx.MockTransport(handle))
    await client.delete([])
    await client.delete(["a.jpg"])

    [request] = seen
    assert request.method == "DELETE"
    assert json.loads(request.content) == {"prefixes": ["a.jpg"]}


async def test_http_failure_becomes_storage_error() -> None:
    client = make_client(
        httpx.MockTransport(lambda request: httpx.Response(500, text="boom"))
    )

    with pytest.raises(StorageError):
        await client.upload("a.jpg", b"x", "image/jpeg")


async def test_missing_key_is_storage_error() -> None:
    client = make_client(
        httpx.MockTransport(lambda request: httpx.Response(200)),
        secret_key="",
    )

    with pytest.raises(StorageError):
        await client.signed_urls(["a.jpg"], 60)
