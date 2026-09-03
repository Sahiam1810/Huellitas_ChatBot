from datetime import UTC, date, datetime
from uuid import UUID

import pytest

from app.modules.appointments.graph import AppointmentsModuleExecutor
from app.modules.appointments.manifest import APPOINTMENTS_MANIFEST
from app.modules.appointments.routing import APPOINTMENTS_ROUTING_RULES
from app.modules.appointments.services.appointment_matcher import select_appointments
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_executor import ModuleExecutionRequest
from app.orchestration.rag_contracts import RagStatus
from app.orchestration.rule_based_intent_router import RuleBasedIntentRouter
from app.ports.appointments_gateway import (
    AppointmentBookingOptions,
    AppointmentBookingPet,
    AppointmentBookingRequest,
    AppointmentBookingService,
    AppointmentBookingSlot,
    AppointmentBookingVeterinarian,
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
        self.created: list[tuple[AppointmentBookingRequest, str]] = []

    async def list_owned(
        self, scope: AppointmentScope, bearer_token: str
    ) -> tuple[AppointmentItem, ...]:
        self.scopes.append(scope)
        if self.error:
            raise self.error
        return self.items

    async def get_owned(self, appointment_id: UUID, bearer_token: str) -> AppointmentItem:
        return self.items[0]

    async def get_booking_options(self, bearer_token: str) -> AppointmentBookingOptions:
        return AppointmentBookingOptions(
            pets=(AppointmentBookingPet(UUID("22222222-2222-2222-2222-222222222222"), "Luna"),),
            services=(
                AppointmentBookingService(
                    UUID("44444444-4444-4444-4444-444444444444"),
                    "Consulta general",
                    30,
                ),
            ),
            veterinarians=(
                AppointmentBookingVeterinarian(
                    UUID("33333333-3333-3333-3333-333333333333"),
                    "Dra. Ana PÃ©rez",
                    "Medicina general",
                ),
            ),
            requires_requester_phone_number=True,
        )

    async def list_booking_slots(
        self,
        veterinarian_id: UUID,
        service_id: UUID,
        booking_date: date,
        bearer_token: str,
    ) -> tuple[AppointmentBookingSlot, ...]:
        assert booking_date == date(2026, 9, 10)
        return (
            AppointmentBookingSlot(
                datetime(2026, 9, 10, 15, tzinfo=UTC),
                datetime(2026, 9, 10, 15, 30, tzinfo=UTC),
            ),
        )

    async def create_owned(
        self,
        booking: AppointmentBookingRequest,
        idempotency_key: str,
        bearer_token: str,
    ) -> AppointmentItem:
        self.created.append((booking, idempotency_key))
        return appointment()

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


def request(message: str, intent: str, pending=None) -> ModuleExecutionRequest:
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
        pending_confirmation=pending,
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


@pytest.mark.anyio
async def test_booking_collects_official_options_and_creates_only_after_confirmation() -> None:
    gateway = Gateway()
    executor = AppointmentsModuleExecutor(gateway, "America/Bogota")

    result = await executor.execute(
        request("Quiero agendar una cita", "appointments.book"), context()
    )
    assert "Luna" in (result.message or "")

    for answer in ("1", "1", "1", "10/09/2026", "1", "3001234567"):
        result = await executor.execute(
            request(answer, "appointments.booking", result.pending_confirmation), context()
        )

    assert "Confirmas" in (result.message or "")
    assert gateway.created == []

    result = await executor.execute(
        request("sí", "appointments.booking", result.pending_confirmation), context()
    )

    assert "agendada correctamente" in (result.message or "")
    assert gateway.created[0][0].pet_id == UUID("22222222-2222-2222-2222-222222222222")
    assert gateway.created[0][0].scheduled_start_utc == datetime(2026, 9, 10, 15, tzinfo=UTC)
    assert gateway.created[0][1] == "appointment-1"
    assert result.pending_confirmation is None


@pytest.mark.anyio
async def test_booking_can_be_cancelled_without_backend_mutation() -> None:
    gateway = Gateway()
    executor = AppointmentsModuleExecutor(gateway, "America/Bogota")
    started = await executor.execute(
        request("Quiero reservar una cita", "appointments.book"), context()
    )

    result = await executor.execute(
        request("cancelar", "appointments.booking", started.pending_confirmation), context()
    )

    assert "Cancelé" in (result.message or "")
    assert result.pending_confirmation is None
    assert gateway.created == []


@pytest.mark.anyio
async def test_booking_request_routes_to_appointments_without_llm() -> None:
    command = request("Quiero agendar una cita", "appointments.book").command

    decision = await RuleBasedIntentRouter(APPOINTMENTS_ROUTING_RULES).route(
        command, (APPOINTMENTS_MANIFEST,)
    )

    assert decision.module_id == "appointments"
    assert decision.intent == "appointments.book"
