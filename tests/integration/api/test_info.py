from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings


def test_info_exposes_only_safe_service_metadata() -> None:
    settings = Settings(
        app_name="Huellitas Test",
        app_version="2.3.4",
        environment="test",
        log_level="DEBUG",
        host="0.0.0.0",
        port=9123,
        _env_file=None,
    )

    with TestClient(create_application(settings)) as client:
        response = client.get("/api/v1/info")

    assert response.status_code == 200
    assert response.json() == {
        "name": "Huellitas Test",
        "version": "2.3.4",
        "environment": "test",
        "api_version": "v1",
    }
    assert "host" not in response.json()
    assert "port" not in response.json()
    assert "log_level" not in response.json()
    assert "checkpoint" not in response.text.lower()
    assert "redis" not in response.text.lower()
