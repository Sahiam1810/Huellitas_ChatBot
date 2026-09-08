from dataclasses import replace
from datetime import UTC, datetime
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
)
from app.ports.pet_profile_gateway import (
    CatalogItem,
    PetProfile,
    PetProfilePatch,
    PetRegistration,
)
from app.ports.token_validator import AuthenticatedPrincipal

CONVERSATION_ID = UUID("10000000-0000-0000-0000-000000000001")
PERSON_ID = UUID("20000000-0000-0000-0000-000000000002")
ACCOUNT_ID = UUID("30000000-0000-0000-0000-000000000003")
PET_ID = UUID("40000000-0000-0000-0000-000000000004")
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


class PetGateway:
    def __init__(self) -> None:
        self.profiles: tuple[PetProfile, ...] = ()
        self.registrations: list[PetRegistration] = []

    async def list_owned(self, bearer_token: str) -> tuple[PetProfile, ...]:
        return self.profiles

    async def create_owned(self, bearer_token: str, registration: PetRegistration) -> PetProfile:
        self.registrations.append(registration)
        profile = PetProfile(
            id=PET_ID,
            name=registration.name,
            age=registration.age,
            gender=registration.gender,
            weight=registration.weight,
            observations=registration.observations,
            species_id=registration.species_id,
            species_name="Canino",
            race_id=registration.race_id,
            race_name="Mestizo",
            updated_at=datetime.now(UTC),
        )
        self.profiles = (profile,)
        return profile

    async def update_owned(
        self, bearer_token: str, pet_id: UUID, patch: PetProfilePatch
    ) -> PetProfile:
        assert self.profiles
        return replace(self.profiles[0], name=patch.name or self.profiles[0].name)

    async def list_species(self, bearer_token: str) -> tuple[CatalogItem, ...]:
        return (CatalogItem(SPECIES_ID, "Canino"),)

    async def list_races(
        self, species_id: UUID, bearer_token: str
    ) -> tuple[CatalogItem, ...]:
        assert species_id == SPECIES_ID
        return (CatalogItem(RACE_ID, "Mestizo"),)

    async def close(self) -> None:
        return None


class AppointmentsGateway:
    def __init__(self, pets: PetGateway) -> None:
        self._pets = pets

    async def get_booking_options(self, bearer_token: str) -> AppointmentBookingOptions:
        return AppointmentBookingOptions(
            pets=tuple(AppointmentBookingPet(item.id, item.name) for item in self._pets.profiles),
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
        roles=("Cliente",),
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
            role="Cliente",
            username="cliente",
            email="cliente@example.test",
            token_id=UUID("b0000000-0000-0000-0000-00000000000b"),
        ),
        execution_id=UUID("c0000000-0000-0000-0000-00000000000c"),
        correlation_id=UUID("90000000-0000-0000-0000-000000000009"),
    )


@pytest.mark.anyio
async def test_booking_without_pets_registers_one_and_resumes_booking() -> None:
    pets = PetGateway()
    graph = build_main_graph(
        NeverGeneral(),
        build_module_registry(
            pets,
            appointments_gateway=AppointmentsGateway(pets),
        ),
        InitialBookingRouter(),
        InMemorySaver(),
    )
    configuration = {"configurable": {"thread_id": str(CONVERSATION_ID)}}
    messages = (
        "Quiero agendar una consulta para mi cachorro",
        "Okey, mi mascota se llama Milou",
        "Canino",
        "Mestizo",
        "2",
        "macho",
        "8 kg",
        "ninguna",
    )

    for sequence, text in enumerate(messages, start=1):
        state = await graph.ainvoke(
            {"command": message_command_to_state(command(text, sequence))},
            config=configuration,
            context=context(),
        )

    assert state["confirmation"]["module_id"] == "pet_profile"
    assert state["confirmation"]["continuation"] == {
        "module_id": "appointments",
        "intent": "appointments.book",
    }

    state = await graph.ainvoke(
        {"command": message_command_to_state(command("sí", len(messages) + 1))},
        config=configuration,
        context=context(),
    )

    result = message_result_from_state(state["result"])
    assert len(pets.registrations) == 1
    assert pets.registrations[0].name == "Milou"
    assert result.module == "appointments"
    assert "Milou fue registrada" in (result.message or "")
    assert "¿Para cuál mascota" in (result.message or "")
    assert state["confirmation"]["module_id"] == "appointments"
