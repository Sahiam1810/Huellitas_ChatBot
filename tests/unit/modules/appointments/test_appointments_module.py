from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.modules.appointments.graph import AppointmentsModuleExecutor
from app.modules.appointments.manifest import APPOINTMENTS_MANIFEST
from app.modules.appointments.services.appointment_matcher import select_appointments
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_executor import ModuleExecutionRequest
from app.orchestration.rag_contracts import RagStatus
from app.ports.appointments_gateway import (
    AppointmentItem,
    AppointmentScope,
    AppointmentsGateway,
    AppointmentsUnavailableError,
)
from app.ports.token_validator import AuthenticatedPrincipal


def appointment(*, pet: str = "Luna", service: str = "Consulta general") -> AppointmentItem:
    return AppointmentItem(
        id=UUID("11111111-1111-1111-1111-111111111111"),
        client_pet_id=UUID("22222222-2222-2222-2222-222222222222"),
        pet_name=pet,
        veterinarian_id=UUID("33333333-3333-3333-3333-333333333333"),
        veterinarian_name="Dra. Ana Pérez",
        service_id=UUID("44444444-4444-4444-4444-444444444444"),
        service_name=service,
        status_id=UUID("55555555-5555-5555-5555-555555555555"),
        status_name="AGENDADA",
        availability_id=UUID("66666666-6666-6666-6666-666666666666"),
        scheduled_start=datetime(2026, 9, 3, 15, tzinfo=UTC),
        scheduled_end=datetime(2026, 9, 3, 15, 30, tzinfo=UTC),
        notes="Control preventivo",
    )


class Gateway(AppointmentsGateway):
    def __init__(self, items: tuple[AppointmentItem, ...] = (appointment(),)) -> None:
        self.items = items
        self.scopes: list[AppointmentScope] = []
        self.error: Exception | None = None

    async def list_owned(
        self, scope: AppointmentScope, bearer_token: str
    ) -> tuple[AppointmentItem, ...]:
        self.scopes.append(scope)
        if self.error:
            raise self.error
        return self.items

    async def get_owned(self, appointment_id: UUID, bearer_token: str) -> AppointmentItem:
        return self.items[0]

    async def close(self) -> None:
        return None


def context() -> ExecutionContext:
    return ExecutionContext(
        bearer_token="token",
        principal=AuthenticatedPrincipal(
            account_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            person_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            role_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
            role="Cliente",
            username="samuel",
            email="samuel@example.com",
            token_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        ),
        execution_id=UUID("eeeeeeee-eeee-eeee-eeee-eeeeeeeeeeee"),
        correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
    )


def request(message: str, intent: str) -> ModuleExecutionRequest:
    return ModuleExecutionRequest(
        command=MessageCommand(
            message=message,
            conversation_id=UUID("10000000-0000-0000-0000-000000000001"),
            user_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            pet_id=None,
            channel="telegram",
            language="es-CO",
            roles=("Cliente",),
            is_escalated=False,
            correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            idempotency_key="appointment-1",
            publish_as_global_knowledge=False,
        ),
        intent=intent,
        manifest=APPOINTMENTS_MANIFEST,
    )


@pytest.mark.anyio
async def test_list_uses_upcoming_and_bogota_time_without_llm_or_rag() -> None:
    gateway = Gateway()
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("¿Qué citas tengo?", "appointments.list"), context()
    )
    assert gateway.scopes == [AppointmentScope.UPCOMING]
    assert "3 de septiembre de 2026, 10:00 a. m." in (result.message or "")
    assert result.rag.status is RagStatus.DISABLED


@pytest.mark.anyio
async def test_history_uses_history_scope() -> None:
    gateway = Gateway()
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("Mis citas pasadas", "appointments.history"), context()
    )
    assert gateway.scopes == [AppointmentScope.HISTORY]
    assert "citas anteriores" in (result.message or "")


@pytest.mark.anyio
async def test_detail_matches_pet_and_returns_official_detail() -> None:
    gateway = Gateway()
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("¿Cuándo es mi cita de Luna?", "appointments.view"), context()
    )
    assert gateway.scopes == [AppointmentScope.ALL]
    assert "Veterinario: Dra. Ana Pérez" in (result.message or "")
    assert "Notas: Control preventivo" in (result.message or "")


def test_matcher_is_accent_and_case_insensitive() -> None:
    item = appointment(pet="Muñeca")
    assert select_appointments("cita de MUNECA", (item,)).appointments == (item,)


@pytest.mark.anyio
async def test_empty_list_is_explicit() -> None:
    result = await AppointmentsModuleExecutor(Gateway(()), "America/Bogota").execute(
        request("Mis citas", "appointments.list"), context()
    )
    assert result.message == "No tienes citas próximas registradas."


@pytest.mark.anyio
async def test_gateway_failure_is_safe() -> None:
    gateway = Gateway()
    gateway.error = AppointmentsUnavailableError("secret host")
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("Mis citas", "appointments.list"), context()
    )
    assert "sistema veterinario" in (result.message or "")
    assert "secret" not in (result.message or "")
