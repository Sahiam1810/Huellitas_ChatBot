from dataclasses import replace
from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.pet_profile.graph import PetProfileModuleExecutor
from app.modules.pet_profile.manifest import PET_PROFILE_MANIFEST
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_executor import ModuleExecutionRequest
from app.ports.pet_profile_gateway import CatalogItem, PetProfile, PetProfilePatch
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.enums import MessageResponseType

PET_ID = UUID("11111111-1111-1111-1111-111111111111")
VERSION = datetime(2026, 9, 2, 15, tzinfo=UTC)


class Gateway:
    def __init__(self) -> None:
        self.profile = PetProfile(
            id=PET_ID,
            name="Luna",
            age=4,
            gender="F",
            weight=12.5,
            observations="Sana",
            species_id=UUID("22222222-2222-2222-2222-222222222222"),
            species_name="Canino",
            race_id=UUID("33333333-3333-3333-3333-333333333333"),
            race_name="Mestizo",
            updated_at=VERSION,
        )
        self.patches: list[PetProfilePatch] = []

    async def list_owned(self, bearer_token: str) -> tuple[PetProfile, ...]:
        assert bearer_token == "jwt-secret"
        return (self.profile,)

    async def update_owned(
        self, bearer_token: str, pet_id: UUID, patch: PetProfilePatch
    ) -> PetProfile:
        assert pet_id == PET_ID
        self.patches.append(patch)
        return replace(self.profile, weight=patch.weight or 12.5)

    async def list_species(self, bearer_token: str) -> tuple[CatalogItem, ...]:
        return (CatalogItem(self.profile.species_id, "Canino"),)

    async def list_races(self, bearer_token: str) -> tuple[CatalogItem, ...]:
        return (CatalogItem(self.profile.race_id, "Mestizo"),)

    async def close(self) -> None:
        return None


class EmptyGateway(Gateway):
    async def list_owned(self, bearer_token: str) -> tuple[PetProfile, ...]:
        return ()


def command(message: str) -> MessageCommand:
    return MessageCommand(
        message=message,
        conversation_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
        user_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=False,
        correlation_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        idempotency_key="pet-1",
    )


def context() -> ExecutionContext:
    return ExecutionContext(
        bearer_token="jwt-secret",
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
async def test_list_returns_owned_pet_without_calling_a_model() -> None:
    executor = PetProfileModuleExecutor(Gateway())
    result = await executor.execute(
        ModuleExecutionRequest(command("¿Qué mascotas tengo?"), "pets.list", PET_PROFILE_MANIFEST),
        context(),
    )

    assert result.response_type is MessageResponseType.RETRIEVED
    assert "Luna" in (result.message or "")
    assert "Canino" in (result.message or "")


@pytest.mark.anyio
async def test_linked_account_without_pets_is_explained_explicitly() -> None:
    executor = PetProfileModuleExecutor(EmptyGateway())

    result = await executor.execute(
        ModuleExecutionRequest(command("¿Qué mascotas tengo?"), "pets.list", PET_PROFILE_MANIFEST),
        context(),
    )

    assert "cuenta está vinculada" in (result.message or "").casefold()
    assert "no encontré mascotas" in (result.message or "").casefold()


@pytest.mark.anyio
async def test_update_waits_for_explicit_confirmation_before_patch() -> None:
    gateway = Gateway()
    executor = PetProfileModuleExecutor(gateway)
    prepared = await executor.execute(
        ModuleExecutionRequest(
            command("Actualiza el peso de Luna a 13.5 kg"),
            "pets.update",
            PET_PROFILE_MANIFEST,
        ),
        context(),
    )

    assert gateway.patches == []
    assert prepared.pending_confirmation is not None
    assert "13.5" in (prepared.message or "")

    confirmed = await executor.execute(
        ModuleExecutionRequest(
            command("sí"),
            "pet_profile.confirmation",
            PET_PROFILE_MANIFEST,
            prepared.pending_confirmation,
        ),
        context(),
    )

    assert gateway.patches[0].weight == 13.5
    assert confirmed.pending_confirmation is None
    assert "actualizado" in (confirmed.message or "").casefold()
