from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings


def build_test_app() -> FastAPI:
    return create_application(Settings(environment="test", _env_file=None))


def test_liveness_reports_process_alive_without_lifespan() -> None:
    app = build_test_app()
    client = TestClient(app)

    response = client.get("/health/live")

    client.close()
    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_reports_ready_inside_lifespan() -> None:
    app = build_test_app()

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 200
    assert response.json() == {"status": "ready"}
    assert app.state.ready is False


def test_readiness_reports_problem_when_lifespan_has_not_started() -> None:
    app = build_test_app()
    client = TestClient(app)

    response = client.get("/health/ready")

    client.close()
    assert response.status_code == 503
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.json() == {
        "type": "about:blank",
        "title": "Service Unavailable",
        "status": 503,
        "detail": "Application is not ready",
        "instance": "/health/ready",
    }
