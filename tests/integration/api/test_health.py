from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.bootstrap import lifecycle
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.shared.exceptions import RuntimeStoreUnavailableError, VectorStoreUnavailableError


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


def test_readiness_reports_problem_when_rag_collections_are_not_ready() -> None:
    app = build_test_app()

    with TestClient(app) as client:
        app.state.rag_collections_ready = False
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"] == "Application is not ready"


def test_readiness_recovers_after_vector_store_becomes_available(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SimpleNamespace(
        check_health=AsyncMock(
            side_effect=[
                VectorStoreUnavailableError("hidden sdk detail"),
                VectorStoreUnavailableError("hidden sdk detail"),
                None,
            ]
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: store)
    app = create_application(
        Settings(
            environment="test",
            vector_store_enabled=True,
            qdrant_startup_max_attempts=1,
            qdrant_startup_retry_delay_seconds=0,
            _env_file=None,
        )
    )

    with TestClient(app) as client:
        degraded = client.get("/health/ready")
        recovered = client.get("/health/ready")

    assert degraded.status_code == 503
    assert degraded.json() == {
        "type": "about:blank",
        "title": "Service Unavailable",
        "status": 503,
        "detail": "Application is not ready",
        "instance": "/health/ready",
    }
    assert "hidden sdk detail" not in degraded.text
    assert recovered.status_code == 200
    assert recovered.json() == {"status": "ready"}


def test_liveness_survives_and_readiness_recovers_after_runtime_store_failure(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    store = SimpleNamespace(
        check_health=AsyncMock(
            side_effect=[
                RuntimeStoreUnavailableError("SENSITIVE REDIS DETAIL"),
                RuntimeStoreUnavailableError("SENSITIVE REDIS DETAIL"),
                None,
            ]
        ),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_runtime_store", lambda settings: store, raising=False)
    app = create_application(
        Settings(
            environment="test",
            redis_enabled=True,
            redis_startup_max_attempts=1,
            redis_startup_retry_delay_seconds=0,
            _env_file=None,
        )
    )

    with TestClient(app) as client:
        live = client.get("/health/live")
        degraded = client.get("/health/ready")
        recovered = client.get("/health/ready")

    assert live.status_code == 200
    assert live.json() == {"status": "alive"}
    assert degraded.status_code == 503
    assert degraded.json()["detail"] == "Application is not ready"
    assert "SENSITIVE REDIS DETAIL" not in degraded.text
    assert recovered.status_code == 200
    assert recovered.json() == {"status": "ready"}


def test_readiness_requires_both_vector_and_runtime_store_when_enabled(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    vector_store = SimpleNamespace(check_health=AsyncMock(), close=AsyncMock())
    runtime_store = SimpleNamespace(
        check_health=AsyncMock(side_effect=[None, RuntimeStoreUnavailableError("hidden")]),
        close=AsyncMock(),
    )
    monkeypatch.setattr(lifecycle, "create_vector_store", lambda settings: vector_store)
    monkeypatch.setattr(
        lifecycle, "create_runtime_store", lambda settings: runtime_store, raising=False
    )
    app = create_application(
        Settings(
            environment="test",
            vector_store_enabled=True,
            qdrant_startup_max_attempts=1,
            qdrant_startup_retry_delay_seconds=0,
            redis_enabled=True,
            redis_startup_max_attempts=1,
            redis_startup_retry_delay_seconds=0,
            _env_file=None,
        )
    )

    with TestClient(app) as client:
        response = client.get("/health/ready")

    assert response.status_code == 503
    assert vector_store.check_health.await_count == 2
    assert runtime_store.check_health.await_count == 2
