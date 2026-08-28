import pytest

from app.orchestration.execution_context import ExecutionContext
from app.orchestration.module_executor import ModuleExecutionRequest, ModuleResult
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.module_registry import (
    ConflictingModuleIntentError,
    DuplicateModuleIdError,
    ModuleNotFoundError,
    ModuleRegistry,
)
from app.shared.enums import MessageResponseType


class Executor:
    async def execute(
        self,
        request: ModuleExecutionRequest,
        context: ExecutionContext,
    ) -> ModuleResult:
        return ModuleResult(
            module_id=request.manifest.module_id,
            message=context.principal.username,
            response_type=MessageResponseType.AI_GENERATED,
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


def test_registry_associates_a_manifest_with_its_neutral_executor() -> None:
    registry = ModuleRegistry()
    appointments = manifest("appointments", "appointments.list")
    executor = Executor()

    registry.register(appointments, executor)

    registration = registry.get_registration("appointments")
    assert registration.manifest is appointments
    assert registration.executor is executor
    assert registry.get("appointments") is appointments
    assert registry.list_registrations() == (registration,)


def test_registry_keeps_scaffold_only_manifests_backward_compatible() -> None:
    registry = ModuleRegistry()
    services = manifest("services_catalog", "services.lookup")

    registry.register(services)

    registration = registry.get_registration("services_catalog")
    assert registration.manifest is services
    assert registration.executor is None


def test_registration_view_is_sorted_without_exposing_mutable_storage() -> None:
    registry = ModuleRegistry()
    registry.register(manifest("services_catalog", "services.lookup"), Executor())
    registry.register(manifest("appointments", "appointments.list"), Executor())

    registrations = registry.list_registrations()

    assert tuple(item.manifest.module_id for item in registrations) == (
        "appointments",
        "services_catalog",
    )
    assert isinstance(registrations, tuple)


def test_missing_registration_uses_the_neutral_not_found_error() -> None:
    with pytest.raises(ModuleNotFoundError, match="missing"):
        ModuleRegistry().get_registration("missing")
