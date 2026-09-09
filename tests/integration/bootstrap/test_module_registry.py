from datetime import UTC, datetime
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from app.bootstrap.application import create_application
from app.bootstrap.module_registry import build_module_registry
from app.bootstrap.settings import Settings
from app.modules.appointments.manifest import APPOINTMENTS_MANIFEST
from app.modules.pet_profile.manifest import PET_PROFILE_MANIFEST
from app.modules.preventive_care.manifest import PREVENTIVE_CARE_MANIFEST
from app.modules.services_catalog.manifest import SERVICES_CATALOG_MANIFEST
from app.modules.veterinary_guidance.manifest import VETERINARY_GUIDANCE_MANIFEST
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_executor import ModuleExecutionRequest
from app.orchestration.module_registry import ModuleRegistry
from app.ports.token_validator import AuthenticatedPrincipal


class PetGateway:
    async def list_owned(self, bearer_token: str) -> tuple[object, ...]:
        return ()

    async def update_owned(self, bearer_token: str, pet_id: object, patch: object) -> object:
        raise AssertionError("not called")

    async def list_species(self, bearer_token: str) -> tuple[object, ...]:
        return ()

    async def list_races(
        self, species_id: object, bearer_token: str
    ) -> tuple[object, ...]:
        return ()

    async def close(self) -> None:
        return None


class ServicesGateway:
    async def list_available(self, bearer_token: str) -> tuple[object, ...]:
        return ()

    async def close(self) -> None:
        return None

class VaccinationsGateway:
    async def list_owned(self, bearer_token: str) -> tuple[object, ...]:
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

    assert module_ids == {
        "appointments",
        "pet_profile",
        "preventive_care",
        "services_catalog",
        "veterinary_guidance",
    }


def test_backend_gateway_registers_private_preventive_care_module() -> None:
    registry = build_module_registry(
        PetGateway(),  # type: ignore[arg-type]
        vaccinations_gateway=VaccinationsGateway(),  # type: ignore[arg-type]
    )
    registration = registry.get_registration("preventive_care")
    assert registration.manifest == PREVENTIVE_CARE_MANIFEST
    assert registration.manifest.guest_accessible is False
    assert registration.executor is not None


def test_backend_gateway_registers_guest_accessible_guidance_module() -> None:
    registry = build_module_registry(PetGateway())  # type: ignore[arg-type]

    registration = registry.get_registration("veterinary_guidance")

    assert registration.manifest == VETERINARY_GUIDANCE_MANIFEST
    assert registration.manifest.guest_accessible is True
    assert registration.executor is not None


@pytest.mark.anyio
async def test_registry_aligns_guidance_offer_ttl_with_appointment_booking() -> None:
    registry = build_module_registry(
        PetGateway(),  # type: ignore[arg-type]
        appointment_booking_ttl_seconds=900,
    )
    registration = registry.get_registration("veterinary_guidance")
    assert registration.executor is not None
    command = MessageCommand(
        message="mi perro no quiere comer",
        conversation_id=UUID("10000000-0000-0000-0000-000000000001"),
        user_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=False,
        correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        idempotency_key="guidance-ttl",
    )
    context = ExecutionContext(
        bearer_token="token",
        principal=AuthenticatedPrincipal(
            account_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            person_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            role_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            role="Cliente",
            username="cliente",
            email="cliente@example.com",
            token_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        ),
        execution_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        correlation_id=command.correlation_id,
    )

    result = await registration.executor.execute(
        ModuleExecutionRequest(
            command=command,
            intent="guidance.ask",
            manifest=registration.manifest,
        ),
        context,
    )

    assert result.pending_confirmation is not None
    remaining_seconds = (
        result.pending_confirmation.expires_at - datetime.now(UTC)
    ).total_seconds()
    assert 895 <= remaining_seconds <= 900


def test_backend_gateway_registers_private_appointments_module() -> None:
    registry = build_module_registry(
        appointments_gateway=AppointmentsGateway(),  # type: ignore[arg-type]
    )
    registration = registry.get_registration("appointments")
    assert registration.manifest == APPOINTMENTS_MANIFEST
    assert registration.manifest.guest_accessible is False
    assert registration.executor is not None
