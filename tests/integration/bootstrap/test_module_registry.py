from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.orchestration.module_registry import ModuleRegistry


def test_application_composes_one_empty_registry_outside_lifespan() -> None:
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))
    registry = app.state.dependencies.module_registry

    assert isinstance(registry, ModuleRegistry)
    assert registry.list_manifests() == ()

    with TestClient(app):
        assert app.state.dependencies.module_registry is registry

    assert app.state.dependencies.module_registry is registry
