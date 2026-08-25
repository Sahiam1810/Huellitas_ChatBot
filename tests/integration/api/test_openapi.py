from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings


def test_documentation_routes_exist_when_enabled() -> None:
    settings = Settings(environment="test", docs_enabled=True, _env_file=None)

    with TestClient(create_application(settings)) as client:
        docs_response = client.get("/docs")
        redoc_response = client.get("/redoc")
        openapi_response = client.get("/openapi.json")

    assert docs_response.status_code == 200
    assert redoc_response.status_code == 200
    assert openapi_response.status_code == 200
    schema = openapi_response.json()
    assert schema["info"]["title"] == "Huellitas ChatBot"
    assert schema["info"]["version"] == "0.1.0"
    assert set(schema["paths"]) == {
        "/api/v1/info",
        "/api/v1/messages",
        "/health/live",
        "/health/ready",
    }
    assert "503" in schema["paths"]["/health/ready"]["get"]["responses"]
    message_operation = schema["paths"]["/api/v1/messages"]["post"]
    assert set(message_operation["responses"]) >= {"200", "422", "502", "503", "504"}
    request_schema = message_operation["requestBody"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].endswith("/MessageRequest")


def test_documentation_routes_are_absent_when_disabled() -> None:
    settings = Settings(environment="test", docs_enabled=False, _env_file=None)

    with TestClient(create_application(settings)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
