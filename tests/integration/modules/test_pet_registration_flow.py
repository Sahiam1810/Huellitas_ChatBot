from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.bootstrap.module_registry import build_module_registry
from app.modules.pet_profile.routing import PET_PROFILE_ROUTING_RULES
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.main_graph import build_main_graph
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.rule_based_intent_router import RuleBasedIntentRouter
from app.orchestration.state import message_command_to_state, message_result_from_state
from app.ports.pet_profile_gateway import (
    CatalogItem,
    PetProfile,
    PetProfilePatch,
    PetRegistration,
)
from app.ports.token_validator import AuthenticatedPrincipal

CONVERSATION_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SPECIES_ID = UUID("22222222-2222-2222-2222-222222222222")
RACE_ID = UUID("33333333-3333-3333-3333-333333333333")


class NeverGeneral:
    def __init__(self) -> None:
        self.calls = 0

    async def process(self, command: MessageCommand) -> MessageResult:
        self.calls += 1
        raise AssertionError("Pet registration must not use the general model")


class Gateway:
    def __init__(self) -> None:
        self.registrations: list[PetRegistration] = []
        self.profile = PetProfile(
            UUID("11111111-1111-1111-1111-111111111111"),
            "Luna",
            4,
            "F",
            12.5,
            None,
            SPECIES_ID,
            "Canino",
            RACE_ID,
            "Mestizo",
            datetime.now(UTC),
        )

    async def list_owned(self, bearer_token: str) -> tuple[PetProfile, ...]:
        return (self.profile,)

    async def update_owned(
        self, bearer_token: str, pet_id: UUID, patch: PetProfilePatch
    ) -> PetProfile:
        return self.profile

    async def create_owned(
        self, bearer_token: str, registration: PetRegistration
    ) -> PetProfile:
        self.registrations.append(registration)
        return replace(self.profile, name=registration.name)

    async def list_species(self, bearer_token: str) -> tuple[CatalogItem, ...]:
        return (CatalogItem(SPECIES_ID, "Canino"),)

    async def list_races(
        self, species_id: UUID, bearer_token: str
    ) -> tuple[CatalogItem, ...]:
        assert species_id == SPECIES_ID
        return (CatalogItem(RACE_ID, "Mestizo"),)

    async def close(self) -> None:
        return None


def command(message: str, sequence: int) -> MessageCommand:
    return MessageCommand(
        message=message,
        conversation_id=CONVERSATION_ID,
        user_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=False,
        correlation_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        idempotency_key=f"telegram-update-{sequence}",
    )


def context() -> ExecutionContext:
    return ExecutionContext(
        bearer_token="delegated-token",
        principal=AuthenticatedPrincipal(
            account_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
            person_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            role_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
            role="Cliente",
            username="cliente",
            email="cliente@test.com",
            token_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
        ),
        execution_id=UUID("12345678-1234-1234-1234-123456789012"),
        correlation_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
    )


@pytest.mark.anyio
async def test_main_graph_preserves_draft_and_creates_once_after_confirmation() -> None:
    gateway = Gateway()
    general = NeverGeneral()
    graph = build_main_graph(
        general,
        build_module_registry(gateway),
        RuleBasedIntentRouter(PET_PROFILE_ROUTING_RULES),
        InMemorySaver(),
    )
    messages = (
        "Quiero registrar una mascota",
        "Luna",
        "Canino",
        "Mestizo",
        "4",
        "hembra",
        "12.5",
        "ninguna",
    )

    for sequence, message in enumerate(messages, start=1):
        current = command(message, sequence)
        state = await graph.ainvoke(
            {"command": message_command_to_state(current)},
            config={"configurable": {"thread_id": str(CONVERSATION_ID)}},
            context=context(),
        )

    assert gateway.registrations == []
    assert "confirmas" in (message_result_from_state(state["result"]).message or "").casefold()

    confirmation = command("sí", len(messages) + 1)
    final_state = await graph.ainvoke(
        {"command": message_command_to_state(confirmation)},
        config={"configurable": {"thread_id": str(CONVERSATION_ID)}},
        context=context(),
    )

    assert len(gateway.registrations) == 1
    assert gateway.registrations[0].name == "Luna"
    assert "registrada" in (
        message_result_from_state(final_state["result"]).message or ""
    ).casefold()
    assert general.calls == 0
