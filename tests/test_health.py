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
