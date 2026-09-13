from datetime import UTC
from uuid import UUID

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.bootstrap.module_registry import build_module_registry
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.intent_router import RoutingDecision
from app.orchestration.main_graph import build_main_graph
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.state import message_command_to_state, message_result_from_state
from app.ports.appointments_gateway import (
    AppointmentBookingOptions,
    AppointmentBookingPet,
    AppointmentBookingService,
    AppointmentBookingVeterinarian,
    BookingCatalogItem,
    InlinePetRegistration,
    OwnerContactRequest,
    OwnerContactResult,
)
from app.ports.token_validator import AuthenticatedPrincipal

CONVERSATION_ID = UUID("10000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("20000000-0000-0000-0000-000000000002")
ACCOUNT_ID = UUID("30000000-0000-0000-0000-000000000003")
PET_ID = UUID("40000000-0000-0000-0000-000000000004")
EXISTING_PET_ID = UUID("40000000-0000-0000-0000-000000000014")
SPECIES_ID = UUID("50000000-0000-0000-0000-000000000005")
RACE_ID = UUID("60000000-0000-0000-0000-000000000006")


class NeverGeneral:
    async def process(self, command: MessageCommand) -> MessageResult:
        raise AssertionError("The cross-module flow must not use the general model")


class InitialBookingRouter:
    async def route(self, command, manifests) -> RoutingDecision:
        return RoutingDecision.module(
            module_id="appointments",
            intent="appointments.book",
        )


class AppointmentsGateway:
    def __init__(self) -> None:
        self.pets: list[AppointmentBookingPet] = []
        self.registrations: list[InlinePetRegistration] = []

    async def get_booking_options(self, bearer_token: str) -> AppointmentBookingOptions:
        return await self.get_booking_options_by_identification("ignored", bearer_token)

    async def get_booking_options_by_identification(
        self, identification_number: str, bearer_token: str
    ) -> AppointmentBookingOptions:
        return AppointmentBookingOptions(
            pets=tuple(self.pets),
            services=(
                AppointmentBookingService(
                    UUID("70000000-0000-0000-0000-000000000007"),
                    "Consulta general",
                    30,
                ),
            ),
            veterinarians=(
                AppointmentBookingVeterinarian(
                    UUID("80000000-0000-0000-0000-000000000008"),
                    "Dra. Ana",
                    "Medicina general",
                ),
            ),
            requires_requester_phone_number=False,
        )

    async def find_or_create_owner(
        self, contact: OwnerContactRequest, bearer_token: str
    ) -> OwnerContactResult:
        return OwnerContactResult(
            client_id=ACCOUNT_ID,
            identification_number=contact.identification_number,
            created=True,
            access_token="delegated-agent-token",
        )

    async def create_pet_by_identification(
        self,
        identification_number: str,
        registration: InlinePetRegistration,
        bearer_token: str,
    ) -> AppointmentBookingPet:
        self.registrations.append(registration)
        pet = AppointmentBookingPet(PET_ID if not self.pets else UUID(int=PET_ID.int + 1), registration.name)
        self.pets.append(pet)
        return pet

    async def list_pet_species(self, bearer_token: str) -> tuple[BookingCatalogItem, ...]:
        return (BookingCatalogItem(SPECIES_ID, "Canino"),)

    async def list_pet_races(
        self, species_id: UUID, bearer_token: str
    ) -> tuple[BookingCatalogItem, ...]:
        assert species_id == SPECIES_ID
        return (BookingCatalogItem(RACE_ID, "Mestizo"),)

    async def close(self) -> None:
        return None


def command(message: str, sequence: int) -> MessageCommand:
    return MessageCommand(
        message=message,
        conversation_id=CONVERSATION_ID,
        user_id=PERSON_ID,
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("TelegramGuest",),
        is_escalated=False,
        correlation_id=UUID("90000000-0000-0000-0000-000000000009"),
        idempotency_key=f"telegram-update-{sequence}",
        publish_as_global_knowledge=False,
    )


def context() -> ExecutionContext:
    return ExecutionContext(
        bearer_token="delegated-token",
        principal=AuthenticatedPrincipal(
            account_id=ACCOUNT_ID,
            person_id=PERSON_ID,
            role_id=UUID("a0000000-0000-0000-0000-00000000000a"),
            role="TelegramGuest",
            username="guest",
            email="guest@example.test",
            token_id=UUID("b0000000-0000-0000-0000-00000000000b"),
        ),
        execution_id=UUID("c0000000-0000-0000-0000-00000000000c"),
        correlation_id=UUID("90000000-0000-0000-0000-000000000009"),
    )


@pytest.mark.anyio
async def test_booking_without_pets_registers_inline_and_continues() -> None:
    appointments = AppointmentsGateway()
    graph = build_main_graph(
        NeverGeneral(),
        build_module_registry(appointments_gateway=appointments),
        InitialBookingRouter(),
        InMemorySaver(),
    )
    configuration = {"configurable": {"thread_id": str(CONVERSATION_ID)}}
    messages = (
        "Quiero agendar una consulta para mi cachorro",
        "1234567890",
        "Ana Pérez",
        "ana@example.com",
        "Milou",
        "Canino",
        "Mestizo",
        "2",
        "macho",
        "8 kg",
        "ninguna",
        "sí",
    )

    for sequence, text in enumerate(messages, start=1):
        state = await graph.ainvoke(
            {"command": message_command_to_state(command(text, sequence))},
            config=configuration,
            context=context(),
        )

    result = message_result_from_state(state["result"])
    assert len(appointments.registrations) == 1
    assert appointments.registrations[0].name == "Milou"
    assert result.module == "appointments"
    assert "Milou fue registrada" in (result.message or "")
    assert state["confirmation"]["module_id"] == "appointments"


@pytest.mark.anyio
async def test_booking_registers_another_pet_inline() -> None:
    appointments = AppointmentsGateway()
    appointments.pets = [AppointmentBookingPet(EXISTING_PET_ID, "Luna")]
    graph = build_main_graph(
        NeverGeneral(),
        build_module_registry(appointments_gateway=appointments),
        InitialBookingRouter(),
        InMemorySaver(),
    )
    configuration = {"configurable": {"thread_id": str(CONVERSATION_ID)}}
    messages = (
        "Quiero agendar una consulta para otra mascota",
        "1234567890",
        "Ana Pérez",
        "ana@example.com",
        "otra",
        "Milou",
        "Canino",
        "Mestizo",
        "2",
        "macho",
        "8 kg",
        "ninguna",
        "sí",
    )

    for sequence, text in enumerate(messages, start=1):
        state = await graph.ainvoke(
            {"command": message_command_to_state(command(text, sequence))},
            config=configuration,
            context=context(),
        )

    result = message_result_from_state(state["result"])
    assert [registration.name for registration in appointments.registrations] == ["Milou"]
    assert result.module == "appointments"
    assert state["confirmation"]["module_id"] == "appointments"
    assert "Luna" in (result.message or "") or "Milou" in (result.message or "")
    assert "Registrar otra mascota" in (result.message or "") or "servicio" in (
        result.message or ""
    ).casefold() or "veterinario" in (result.message or "").casefold()
