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
