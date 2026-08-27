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
    access_token_scheme = schema["components"]["securitySchemes"]["AccessToken"]
    assert access_token_scheme["type"] == "http"
    assert access_token_scheme["scheme"] == "bearer"
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
    assert message_operation["security"] == [{"AccessToken": []}]
    assert set(message_operation["responses"]) >= {
        "200",
        "401",
        "403",
        "409",
        "422",
        "502",
        "503",
        "504",
    }
    replay_header = message_operation["responses"]["200"]["headers"]["Idempotency-Replayed"]
    assert replay_header["schema"] == {"type": "string"}
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
    assert "idempotencyReplayed" not in message_response["properties"]
    assert set(schema["components"]["schemas"]["RagStatus"]["enum"]) == {
        "disabled",
        "skipped",
        "empty",
        "used",
        "degraded",
    }
    assert set(schema["components"]["schemas"]["SemanticRoute"]["enum"]) == {
        "direct",
        "contextual",
        "general",
        "disabled",
        "skipped",
        "degraded",
    }
    rag_response = schema["components"]["schemas"]["RagResponse"]
    assert {"route", "topScore"} <= set(rag_response["required"])
    assert rag_response["properties"]["route"]["$ref"].endswith("/SemanticRoute")
    assert {"retrieved", "ai_generated", "human_controlled"} == set(
        schema["components"]["schemas"]["MessageResponseType"]["enum"]
    )
    documents = schema["paths"]["/api/v1/knowledge/documents"]
    assert set(documents) == {"get", "post"}
    assert set(documents["post"]["responses"]) >= {"201", "409", "422", "502", "503", "504"}
    item = schema["paths"]["/api/v1/knowledge/documents/{documentId}"]
    assert set(item) == {"get", "put", "delete"}
    assert "204" in item["delete"]["responses"]
    for path, path_item in schema["paths"].items():
        if path.startswith("/api/v1/knowledge/documents"):
            for operation in path_item.values():
                assert operation["security"] == [{"AccessToken": []}]
                assert {"401", "403"} <= set(operation["responses"])
    assert "security" not in schema["paths"]["/health/live"]["get"]
    assert "security" not in schema["paths"]["/health/ready"]["get"]
    assert "security" not in schema["paths"]["/api/v1/info"]["get"]
    assert all("embeddings" not in path for path in schema["paths"])


def test_documentation_routes_are_absent_when_disabled() -> None:
    settings = Settings(environment="test", docs_enabled=False, _env_file=None)

    with TestClient(create_application(settings)) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404
