from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.module_registry import build_module_registry
from app.bootstrap.settings import Settings
from app.modules.pet_profile.manifest import PET_PROFILE_MANIFEST
from app.orchestration.module_registry import ModuleRegistry


class PetGateway:
    async def list_owned(self, bearer_token: str) -> tuple[object, ...]:
        return ()

    async def update_owned(self, bearer_token: str, pet_id: object, patch: object) -> object:
        raise AssertionError("not called")

    async def list_species(self, bearer_token: str) -> tuple[object, ...]:
        return ()

    async def list_races(self, bearer_token: str) -> tuple[object, ...]:
        return ()

    async def close(self) -> None:
        return None


def test_application_composes_one_empty_registry_outside_lifespan() -> None:
    app = create_application(Settings(environment="test", chat_enabled=False, _env_file=None))
    registry = app.state.dependencies.module_registry

    assert isinstance(registry, ModuleRegistry)
    assert registry.list_manifests() == ()

    with TestClient(app):
        assert app.state.dependencies.module_registry is registry

    assert app.state.dependencies.module_registry is registry


def test_backend_gateway_registers_executable_pet_profile_module() -> None:
    registry = build_module_registry(PetGateway())  # type: ignore[arg-type]

    registration = registry.get_registration("pet_profile")
    assert registration.manifest == PET_PROFILE_MANIFEST
    assert registration.executor is not None
