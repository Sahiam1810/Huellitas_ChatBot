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
        "/api/v1/knowledge/documents",
        "/api/v1/knowledge/documents/{documentId}",
        "/api/v1/knowledge/documents/{documentId}/status",
        "/api/v1/knowledge/documents/{documentId}/restore",
        "/health/live",
        "/health/ready",
    }
    assert "503" in schema["paths"]["/health/ready"]["get"]["responses"]
    message_operation = schema["paths"]["/api/v1/messages"]["post"]
    assert set(message_operation["responses"]) >= {"200", "422", "502", "503", "504"}
    request_schema = message_operation["requestBody"]["content"]["application/json"]["schema"]
    assert request_schema["$ref"].endswith("/MessageRequest")
    request_component = schema["components"]["schemas"]["MessageRequest"]
    publication = request_component["properties"]["publishAsGlobalKnowledge"]
    assert publication["default"] is False
    assert "publishAsGlobalKnowledge" not in request_component["required"]
    response_schema = message_operation["responses"]["200"]["content"]["application/json"]["schema"]
    assert response_schema["$ref"].endswith("/MessageResponse")
    message_response = schema["components"]["schemas"]["MessageResponse"]
    assert message_response["properties"]["rag"]["$ref"].endswith("/RagResponse")
    assert set(schema["components"]["schemas"]["RagStatus"]["enum"]) == {
        "disabled",
        "skipped",
        "empty",
        "used",
        "degraded",
    }
    documents = schema["paths"]["/api/v1/knowledge/documents"]
    assert set(documents) == {"get", "post"}
    assert set(documents["post"]["responses"]) >= {"201", "409", "422", "502", "503", "504"}
    item = schema["paths"]["/api/v1/knowledge/documents/{documentId}"]
    assert set(item) == {"get", "put", "delete"}
    assert "204" in item["delete"]["responses"]
    assert all("embeddings" not in path for path in schema["paths"])


def test_documentation_routes_are_absent_when_disabled() -> None:
    settings = Settings(environment="test", docs_enabled=False, _env_file=None)

    with TestClient(create_application(settings)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
