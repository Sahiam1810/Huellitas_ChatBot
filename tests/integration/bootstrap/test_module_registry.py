from datetime import UTC, datetime
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient
from langgraph.checkpoint.memory import InMemorySaver

from app.bootstrap.application import create_application
from app.bootstrap.module_registry import build_module_registry
from app.bootstrap.settings import Settings
from app.modules.appointments.manifest import APPOINTMENTS_MANIFEST
from app.modules.pet_profile.manifest import PET_PROFILE_MANIFEST
from app.modules.preventive_care.manifest import PREVENTIVE_CARE_MANIFEST
from app.modules.services_catalog.manifest import SERVICES_CATALOG_MANIFEST
from app.modules.services_catalog.routing import SERVICES_CATALOG_ROUTING_RULES
from app.modules.veterinary_guidance.manifest import VETERINARY_GUIDANCE_MANIFEST
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.main_graph import build_main_graph
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.module_executor import ModuleExecutionRequest
from app.orchestration.module_registry import ModuleRegistry
from app.orchestration.rule_based_intent_router import RuleBasedIntentRouter
from app.orchestration.state import message_command_to_state, message_result_from_state
from app.ports.appointments_gateway import (
    AppointmentBookingOptions,
    AppointmentBookingPet,
    AppointmentBookingService,
    AppointmentBookingVeterinarian,
)
from app.ports.services_catalog_gateway import ServiceCatalogItem
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.enums import AccessRequirement


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


def test_backend_gateway_registers_guest_accessible_appointments_module() -> None:
    registry = build_module_registry(
        appointments_gateway=AppointmentsGateway(),  # type: ignore[arg-type]
    )
    registration = registry.get_registration("appointments")
    assert registration.manifest == APPOINTMENTS_MANIFEST
    assert registration.manifest.guest_accessible is True
    assert registration.executor is not None


INTERNAL_MEDICINE_ID = UUID("33333333-3333-3333-3333-333333333333")
CONVERSATION_ID = UUID("10000000-0000-0000-0000-000000000001")


class FlowCatalogGateway:
    async def list_available(self, bearer_token: str) -> tuple[ServiceCatalogItem, ...]:
        return (
            ServiceCatalogItem(
                id=UUID("11111111-1111-1111-1111-111111111111"),
                type_service_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                type_service_name="Consulta",
                name="Consulta general",
                duration_minutes=30,
                price=Decimal("55000"),
            ),
            ServiceCatalogItem(
                id=UUID("22222222-2222-2222-2222-222222222222"),
                type_service_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
                type_service_name="Consulta",
                name="Consulta especializada",
                duration_minutes=45,
                price=Decimal("85000"),
            ),
            ServiceCatalogItem(
                id=INTERNAL_MEDICINE_ID,
                type_service_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
                type_service_name="Procedimiento",
                name="Medicina interna",
                duration_minutes=30,
                price=Decimal("45000"),
            ),
        )

    async def close(self) -> None:
        return None


class FlowAppointmentsGateway:
    async def list_owned(self, scope: object, bearer_token: str) -> tuple[object, ...]:
        return ()

    async def get_owned(self, appointment_id: object, bearer_token: str) -> object:
        raise AssertionError("not called")

    async def get_booking_options(self, bearer_token: str) -> AppointmentBookingOptions:
        return await self.get_booking_options_by_identification("ignored", bearer_token)

    async def get_booking_options_by_identification(
        self, identification_number: str, bearer_token: str
    ) -> AppointmentBookingOptions:
        return AppointmentBookingOptions(
            pets=(AppointmentBookingPet(UUID("22222222-2222-2222-2222-222222222222"), "Luna"),),
            services=(
                AppointmentBookingService(
                    UUID("44444444-4444-4444-4444-444444444444"),
                    "Consulta general",
                    30,
                ),
                AppointmentBookingService(INTERNAL_MEDICINE_ID, "Medicina interna", 30),
            ),
            veterinarians=(
                AppointmentBookingVeterinarian(
                    UUID("55555555-5555-5555-5555-555555555555"),
                    "Dra. Ana Pérez",
                    "Medicina general",
                ),
            ),
            requires_requester_phone_number=True,
        )

    async def find_or_create_owner(self, contact, bearer_token: str):
        from app.ports.appointments_gateway import OwnerContactResult

        return OwnerContactResult(
            client_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            identification_number=contact.identification_number,
            created=False,
            access_token="delegated-agent-token",
        )

    async def list_by_identification(self, *args: object, **kwargs: object) -> tuple[object, ...]:
        return ()

    async def get_by_identification(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("not called")

    async def create_by_identification(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("not called")

    async def cancel_by_identification(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("not called")

    async def reschedule_by_identification(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("not called")

    async def create_pet_by_identification(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("not called")

    async def list_pet_species(self, bearer_token: str) -> tuple[object, ...]:
        return ()

    async def list_pet_races(self, species_id: object, bearer_token: str) -> tuple[object, ...]:
        return ()

    async def list_booking_slots(self, *args: object, **kwargs: object) -> tuple[object, ...]:
        raise AssertionError("not called")

    async def create_owned(self, *args: object, **kwargs: object) -> object:
        raise AssertionError("not called")

    async def cancel_owned(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("not called")

    async def reschedule_owned(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("not called")

    async def request_reschedule_code(self, *args: object, **kwargs: object) -> UUID:
        raise AssertionError("not called")

    async def confirm_reschedule_code(self, *args: object, **kwargs: object) -> None:
        raise AssertionError("not called")

    async def close(self) -> None:
        return None


class NeverGeneral:
    async def process(self, command: MessageCommand) -> MessageResult:
        raise AssertionError(f"unexpected general fallback: {command.message}")


def flow_command(message: str, *, roles: tuple[str, ...], key: str) -> MessageCommand:
    return MessageCommand(
        message=message,
        conversation_id=CONVERSATION_ID,
        user_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=roles,
        is_escalated=False,
        correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        idempotency_key=key,
        publish_as_global_knowledge=False,
    )


def flow_context(role: str) -> ExecutionContext:
    return ExecutionContext(
        bearer_token="token",
        principal=AuthenticatedPrincipal(
            account_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            person_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            role_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            role=role,
            username="user",
            email="user@example.com",
            token_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        ),
        execution_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
    )


def flow_graph(*, booking_ttl: int = 600):
    registry = build_module_registry(
        services_catalog_gateway=FlowCatalogGateway(),  # type: ignore[arg-type]
        appointments_gateway=FlowAppointmentsGateway(),  # type: ignore[arg-type]
        appointment_booking_ttl_seconds=booking_ttl,
    )
    return build_main_graph(
        NeverGeneral(),
        registry,
        RuleBasedIntentRouter(SERVICES_CATALOG_ROUTING_RULES),
        InMemorySaver(),
    )


@pytest.mark.anyio
async def test_registry_aligns_catalog_selection_ttl_with_appointment_booking() -> None:
    registry = build_module_registry(
        services_catalog_gateway=FlowCatalogGateway(),  # type: ignore[arg-type]
        appointment_booking_ttl_seconds=900,
    )
    registration = registry.get_registration("services_catalog")
    assert registration.executor is not None
    result = await registration.executor.execute(
        ModuleExecutionRequest(
            command=flow_command(
                "qué servicios ofrecen",
                roles=("TelegramGuest",),
                key="catalog-ttl",
            ),
            intent="services.list",
            manifest=registration.manifest,
        ),
        flow_context("TelegramGuest"),
    )

    assert result.pending_confirmation is not None
    remaining_seconds = (
        result.pending_confirmation.expires_at - datetime.now(UTC)
    ).total_seconds()
    assert 895 <= remaining_seconds <= 900


@pytest.mark.anyio
@pytest.mark.parametrize("selection", ("3", "quiero medicina interna"))
async def test_authenticated_catalog_selection_starts_booking_with_service(
    selection: str,
) -> None:
    graph = flow_graph()
    config = {"configurable": {"thread_id": str(CONVERSATION_ID)}}
    context = flow_context("Cliente")

    listed = await graph.ainvoke(
        {
            "command": message_command_to_state(
                flow_command(
                    "qué servicios ofrecen",
                    roles=("Cliente",),
                    key="list",
                )
            )
        },
        config=config,
        context=context,
    )
    listed_result = message_result_from_state(listed["result"])
    assert "3. Medicina interna" in (listed_result.message or "")

    selected = await graph.ainvoke(
        {
            "command": message_command_to_state(
                flow_command(selection, roles=("Cliente",), key="select")
            )
        },
        config=config,
        context=context,
    )
    selected_result = message_result_from_state(selected["result"])
    assert "Medicina interna" in (selected_result.message or "")
    assert "deseas agendar" in (selected_result.message or "").casefold()

    booked = await graph.ainvoke(
        {
            "command": message_command_to_state(
                flow_command("sí", roles=("Cliente",), key="accept")
            )
        },
        config=config,
        context=context,
    )
    booked_result = message_result_from_state(booked["result"])
    assert booked_result.module == "appointments"
    assert "mascota" in (booked_result.message or "").casefold()
    assert booked["confirmation"]["payload"]["service_name"] == "Medicina interna"
    assert booked["confirmation"]["payload"]["service_id"] == str(INTERNAL_MEDICINE_ID)
    assert booked["confirmation"]["payload"]["step"] == "pet"


@pytest.mark.anyio
async def test_guest_catalog_selection_requests_identity_and_keeps_service_name() -> None:
    graph = flow_graph()
    config = {"configurable": {"thread_id": str(CONVERSATION_ID)}}
    context = flow_context("TelegramGuest")
    roles = ("TelegramGuest",)

    await graph.ainvoke(
        {
            "command": message_command_to_state(
                flow_command("qué servicios ofrecen", roles=roles, key="list")
            )
        },
        config=config,
        context=context,
    )
    await graph.ainvoke(
        {
            "command": message_command_to_state(
                flow_command("3", roles=roles, key="select")
            )
        },
        config=config,
        context=context,
    )
    accepted = await graph.ainvoke(
        {
            "command": message_command_to_state(
                flow_command("sí", roles=roles, key="accept")
            )
        },
        config=config,
        context=context,
    )
    result = message_result_from_state(accepted["result"])
    assert result.access_requirement is AccessRequirement.IDENTITY_VERIFICATION
    assert result.resume_message == "Quiero agendar una cita para Medicina interna"
    assert result.module == "services_catalog"
