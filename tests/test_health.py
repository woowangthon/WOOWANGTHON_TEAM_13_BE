from fastapi.testclient import TestClient

from app.app import app

client = TestClient(app)


def test_root() -> None:
    response = client.get("/")

    assert response.status_code == 200
    assert response.json() == {"message": "WOOWANGTHON API"}


def test_health_live() -> None:
    response = client.get("/api/v1/health/live")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_openapi_exposes_bearer_authentication() -> None:
    response = client.get("/openapi.json")

    assert response.status_code == 200
    security_scheme = response.json()["components"]["securitySchemes"]["BearerAuth"]
    assert security_scheme["type"] == "http"
    assert security_scheme["scheme"] == "bearer"
    assert security_scheme["bearerFormat"] == "JWT"


def test_cors_allows_local_frontend_with_authorization_header() -> None:
    response = client.options(
        "/api/v1/health/live",
        headers={
            "Origin": "http://localhost:5173",
            "Access-Control-Request-Method": "GET",
            "Access-Control-Request-Headers": "Authorization",
        },
    )

    assert response.status_code == 200
    assert response.headers["access-control-allow-origin"] == (
        "http://localhost:5173"
    )
    assert "authorization" in response.headers[
        "access-control-allow-headers"
    ].lower()


def test_cors_does_not_allow_unknown_origin() -> None:
    response = client.options(
        "/api/v1/health/live",
        headers={
            "Origin": "https://unknown.example",
            "Access-Control-Request-Method": "GET",
        },
    )

    assert "access-control-allow-origin" not in response.headers
