from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.module_registry import build_module_registry
from app.bootstrap.settings import Settings
from app.modules.appointments.manifest import APPOINTMENTS_MANIFEST
from app.modules.pet_profile.manifest import PET_PROFILE_MANIFEST
from app.modules.services_catalog.manifest import SERVICES_CATALOG_MANIFEST
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


class ServicesGateway:
    async def list_available(self, bearer_token: str) -> tuple[object, ...]:
        return ()

    async def close(self) -> None:
        return None


class AppointmentsGateway:
    async def list_owned(self, scope: object, bearer_token: str) -> tuple[object, ...]:
        return ()

    async def get_owned(self, appointment_id: object, bearer_token: str) -> object:
        raise AssertionError("not called")

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


def test_backend_gateway_registers_executable_services_catalog_module() -> None:
    registry = build_module_registry(
        services_catalog_gateway=ServicesGateway(),  # type: ignore[arg-type]
    )

    registration = registry.get_registration("services_catalog")

    assert registration.manifest == SERVICES_CATALOG_MANIFEST
    assert registration.manifest.guest_accessible is True
    assert registration.executor is not None


def test_lifecycle_registers_both_backend_modules() -> None:
    app = create_application(
        Settings(
            environment="test",
            chat_enabled=False,
            backend_enabled=True,
            backend_base_url="http://backend.test",
            _env_file=None,
        )
    )

    with TestClient(app):
        module_ids = {
            manifest.module_id
            for manifest in app.state.dependencies.module_registry.list_manifests()
        }

    assert module_ids == {"appointments", "pet_profile", "services_catalog"}


def test_backend_gateway_registers_private_appointments_module() -> None:
    registry = build_module_registry(
        appointments_gateway=AppointmentsGateway(),  # type: ignore[arg-type]
    )
    registration = registry.get_registration("appointments")
    assert registration.manifest == APPOINTMENTS_MANIFEST
    assert registration.manifest.guest_accessible is False
    assert registration.executor is not None
