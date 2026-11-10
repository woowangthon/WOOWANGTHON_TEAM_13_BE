from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient
from sqlalchemy.exc import DBAPIError
from sqlalchemy.exc import TimeoutError as PoolTimeoutError

from app.app import configure_middlewares
from app.db.session import engine

ORIGIN = "https://woowangthon-team-13-fe.vercel.app"


def make_client() -> TestClient:
    test_app = FastAPI()
    configure_middlewares(test_app, [ORIGIN])

    @test_app.get("/ok")
    async def ok() -> dict[str, str]:
        return {"status": "ok"}

    @test_app.get("/boom")
    async def boom() -> None:
        raise RuntimeError("unexpected")

    @test_app.get("/pool-timeout")
    async def pool_timeout() -> None:
        raise PoolTimeoutError("QueuePool limit reached")

    @test_app.get("/max-clients")
    async def max_clients() -> None:
        raise DBAPIError(
            "SELECT 1",
            None,
            Exception("(EMAXCONNSESSION) max clients reached in session mode"),
        )

    @test_app.get("/missing")
    async def missing() -> None:
        raise HTTPException(status_code=404, detail="Store not found")

    return TestClient(test_app, raise_server_exceptions=False)


def test_unhandled_error_is_json_500_with_cors_header() -> None:
    response = make_client().get("/boom", headers={"Origin": ORIGIN})

    assert response.status_code == 500
    assert response.json()["code"] == "INTERNAL_SERVER_ERROR"
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_db_busy_errors_are_503_with_cors_header() -> None:
    client = make_client()

    for path in ("/pool-timeout", "/max-clients"):
        response = client.get(path, headers={"Origin": ORIGIN})
        assert response.status_code == 503
        assert response.json()["code"] == "DATABASE_BUSY"
        assert response.headers["access-control-allow-origin"] == ORIGIN


def test_normal_and_http_errors_are_unchanged() -> None:
    client = make_client()

    ok = client.get("/ok", headers={"Origin": ORIGIN})
    missing = client.get("/missing", headers={"Origin": ORIGIN})

    assert ok.json() == {"status": "ok"}
    assert ok.headers["access-control-allow-origin"] == ORIGIN
    assert missing.status_code == 404
    assert missing.json() == {"detail": "Store not found"}
    assert missing.headers["access-control-allow-origin"] == ORIGIN


def test_unknown_origin_gets_no_cors_header() -> None:
    response = make_client().get("/boom", headers={"Origin": "https://evil.example"})

    assert response.status_code == 500
    assert "access-control-allow-origin" not in response.headers


def test_engine_pool_does_not_overflow_by_default() -> None:
    pool = engine.pool

    assert pool.size() == 5  # type: ignore[attr-defined]
    assert pool._max_overflow == 0  # type: ignore[attr-defined]
