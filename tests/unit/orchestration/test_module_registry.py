import pytest

from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.module_registry import (
    ConflictingModuleIntentError,
    DuplicateModuleIdError,
    ModuleNotFoundError,
    ModuleRegistry,
)


def manifest(module_id: str, *intents: str) -> ModuleManifest:
    return ModuleManifest(
        module_id=module_id,
        version="1.0.0",
        description=f"{module_id} module",
        intents=intents,
    )


def test_registry_registers_and_discovers_manifests() -> None:
    registry = ModuleRegistry()
    services = manifest("services_catalog", "services.lookup")
    appointments = manifest("appointments", "appointments.list")

    registry.register(services)
    registry.register(appointments)

    assert registry.get("services_catalog") is services
    assert registry.find_by_intent("appointments.list") is appointments
    assert registry.list_manifests() == (appointments, services)


def test_registry_rejects_duplicate_module_ids_without_replacing_original() -> None:
    registry = ModuleRegistry()
    original = manifest("services_catalog", "services.lookup")
    registry.register(original)

    with pytest.raises(DuplicateModuleIdError, match="services_catalog"):
        registry.register(manifest("services_catalog", "services.pricing"))

    assert registry.get("services_catalog") is original
    with pytest.raises(ModuleNotFoundError, match="services.pricing"):
        registry.find_by_intent("services.pricing")


def test_registry_rejects_conflicting_intents_atomically() -> None:
    registry = ModuleRegistry()
    registry.register(manifest("services_catalog", "services.lookup"))

    with pytest.raises(ConflictingModuleIntentError, match="services.lookup"):
        registry.register(manifest("appointments", "appointments.list", "services.lookup"))

    with pytest.raises(ModuleNotFoundError, match="appointments"):
        registry.get("appointments")
    with pytest.raises(ModuleNotFoundError, match="appointments.list"):
        registry.find_by_intent("appointments.list")


def test_registry_raises_neutral_not_found_errors() -> None:
    registry = ModuleRegistry()

    with pytest.raises(ModuleNotFoundError, match="missing_module"):
        registry.get("missing_module")
    with pytest.raises(ModuleNotFoundError, match="missing.intent"):
        registry.find_by_intent("missing.intent")


def test_empty_registry_returns_an_immutable_empty_view() -> None:
    assert ModuleRegistry().list_manifests() == ()
