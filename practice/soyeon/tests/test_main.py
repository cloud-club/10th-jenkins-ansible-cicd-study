from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)


def test_health() -> None:
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.json()["status"] == "ok"
    assert response.json()["service"] == "soyeon-app"


def test_version_uses_environment(monkeypatch) -> None:
    monkeypatch.setenv("APP_VERSION", "42")
    monkeypatch.setenv("RELEASE_ID", "build-42")
    monkeypatch.setenv("GIT_REVISION", "abc1234")
    monkeypatch.setenv("INSTANCE_ID", "app-1")

    response = client.get("/version")

    assert response.status_code == 200
    assert response.json()["version"] == "42"
    assert response.json()["release"] == "build-42"
    assert response.json()["revision"] == "abc1234"
    assert response.json()["instance"] == "app-1"
