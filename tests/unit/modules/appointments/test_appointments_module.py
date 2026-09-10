from dataclasses import replace
from datetime import UTC, date, datetime, timedelta
from uuid import UUID

import pytest

from app.modules.appointments.graph import AppointmentsModuleExecutor
from app.modules.appointments.manifest import APPOINTMENTS_MANIFEST
from app.modules.appointments.routing import APPOINTMENTS_ROUTING_RULES
from app.modules.appointments.services.appointment_matcher import select_appointments
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_executor import ModuleContinuation, ModuleExecutionRequest
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

DEFAULT_ACCOUNT_ID = UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa")
SLOT_AVAILABILITY_ID = UUID("77777777-7777-7777-7777-777777777777")


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
                SLOT_AVAILABILITY_ID,
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

    async def cancel_owned(
        self, appointment_id: UUID, bearer_token: str, *, comment: str | None = None
    ) -> None:
        raise NotImplementedError

    async def request_reschedule_code(
        self,
        appointment_id: UUID,
        phone: str,
        availability_id: UUID,
        scheduled_start_utc: datetime,
        scheduled_end_utc: datetime,
        bearer_token: str,
    ) -> UUID:
        raise NotImplementedError

    async def confirm_reschedule_code(
        self,
        appointment_id: UUID,
        phone: str,
        code: str,
        bearer_token: str,
    ) -> None:
        raise NotImplementedError

    async def close(self) -> None:
        return None


def context(
    account_id: UUID = DEFAULT_ACCOUNT_ID,
) -> ExecutionContext:
    return ExecutionContext(
        bearer_token="token",
        principal=AuthenticatedPrincipal(
            account_id=account_id,
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
async def test_booking_activity_refreshes_expiration() -> None:
    executor = AppointmentsModuleExecutor(
        Gateway(),
        "America/Bogota",
        booking_ttl_seconds=600,
    )
    started = await executor.execute(
        request("Quiero agendar una cita", "appointments.book"), context()
    )
    near_expiration = datetime.now(UTC) + timedelta(seconds=5)
    pending = replace(started.pending_confirmation, expires_at=near_expiration)

    advanced = await executor.execute(
        request("1", "appointments.booking", pending), context()
    )

    assert advanced.pending_confirmation is not None
    assert advanced.pending_confirmation.expires_at > near_expiration + timedelta(minutes=9)


@pytest.mark.anyio
async def test_booking_natural_date_queries_selected_veterinarian_availability() -> None:
    class RecordingSlotsGateway(Gateway):
        def __init__(self) -> None:
            super().__init__()
            self.slot_requests: list[tuple[UUID, UUID, date]] = []

        async def list_booking_slots(
            self,
            veterinarian_id: UUID,
            service_id: UUID,
            booking_date: date,
            bearer_token: str,
        ) -> tuple[AppointmentBookingSlot, ...]:
            self.slot_requests.append((veterinarian_id, service_id, booking_date))
            return (
                AppointmentBookingSlot(
                    SLOT_AVAILABILITY_ID,
                    datetime(2026, 9, 15, 15, tzinfo=UTC),
                    datetime(2026, 9, 15, 15, 30, tzinfo=UTC),
                ),
            )

    gateway = RecordingSlotsGateway()
    executor = AppointmentsModuleExecutor(
        gateway,
        "America/Bogota",
        today_provider=lambda: date(2026, 9, 8),
    )
    result = await executor.execute(
        request("Quiero agendar una cita", "appointments.book"), context()
    )
    for answer in ("1", "1", "1"):
        result = await executor.execute(
            request(answer, "appointments.booking", result.pending_confirmation), context()
        )

    result = await executor.execute(
        request(
            "la quiero para el martes de la próxima semana",
            "appointments.booking",
            result.pending_confirmation,
        ),
        context(),
    )

    assert gateway.slot_requests == [
        (
            UUID("33333333-3333-3333-3333-333333333333"),
            UUID("44444444-4444-4444-4444-444444444444"),
            date(2026, 9, 15),
        )
    ]
    assert "horario" in (result.message or "").casefold()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "slot"


@pytest.mark.anyio
async def test_booking_selects_an_available_natural_date_and_time_directly() -> None:
    executor = AppointmentsModuleExecutor(
        Gateway(),
        "America/Bogota",
        today_provider=lambda: date(2026, 9, 9),
    )
    result = await executor.execute(
        request("Quiero agendar una cita", "appointments.book"), context()
    )
    for answer in ("1", "1", "1"):
        result = await executor.execute(
            request(answer, "appointments.booking", result.pending_confirmation), context()
        )

    result = await executor.execute(
        request(
            "jueves 10 de septiembre a las 10 de la mañana",
            "appointments.booking",
            result.pending_confirmation,
        ),
        context(),
    )

    assert result.message == "Indica un teléfono de contacto entre 7 y 20 dígitos."
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "phone"
    assert result.pending_confirmation.payload["scheduled_start_utc"] == "2026-09-10T15:00:00Z"


@pytest.mark.anyio
async def test_booking_rejects_an_unavailable_natural_time_and_shows_current_slots() -> None:
    executor = AppointmentsModuleExecutor(
        Gateway(),
        "America/Bogota",
        today_provider=lambda: date(2026, 9, 9),
    )
    result = await executor.execute(
        request("Quiero agendar una cita", "appointments.book"), context()
    )
    for answer in ("1", "1", "1"):
        result = await executor.execute(
            request(answer, "appointments.booking", result.pending_confirmation), context()
        )

    result = await executor.execute(
        request(
            "jueves 10 de septiembre a las 11 de la mañana",
            "appointments.booking",
            result.pending_confirmation,
        ),
        context(),
    )

    assert "11:00 a. m. no está disponible" in (result.message or "")
    assert "1. 10 de septiembre de 2026, 10:00 a. m." in (result.message or "")
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "slot"


@pytest.mark.anyio
async def test_booking_professional_date_prompt_and_availability_discovery() -> None:
    class DiscoveryGateway(Gateway):
        def __init__(self) -> None:
            super().__init__()
            self.slot_requests: list[tuple[UUID, UUID, date]] = []

        async def list_booking_slots(
            self,
            veterinarian_id: UUID,
            service_id: UUID,
            booking_date: date,
            bearer_token: str,
        ) -> tuple[AppointmentBookingSlot, ...]:
            self.slot_requests.append((veterinarian_id, service_id, booking_date))
            if booking_date not in {date(2026, 9, 9), date(2026, 9, 11)}:
                return ()
            return (
                AppointmentBookingSlot(
                    SLOT_AVAILABILITY_ID,
                    datetime(2026, 9, booking_date.day, 15, tzinfo=UTC),
                    datetime(2026, 9, booking_date.day, 15, 30, tzinfo=UTC),
                ),
            )

    gateway = DiscoveryGateway()
    executor = AppointmentsModuleExecutor(
        gateway,
        "America/Bogota",
        today_provider=lambda: date(2026, 9, 8),
        availability_search_days=14,
        availability_max_dates=2,
    )
    result = await executor.execute(
        request("Quiero agendar una cita", "appointments.book"), context()
    )
    for answer in ("1", "1", "1"):
        result = await executor.execute(
            request(answer, "appointments.booking", result.pending_confirmation), context()
        )

    assert result.message == "¿Para qué fecha deseas agendar la cita?"
    expiration_before_discovery = result.pending_confirmation.expires_at

    result = await executor.execute(
        request(
            "¿Qué días hay disponibles?",
            "appointments.booking",
            result.pending_confirmation,
        ),
        context(),
    )

    assert "disponibilidad con" in (result.message or "").casefold()
    assert "miércoles 9 de septiembre" in (result.message or "").casefold()
    assert "viernes 11 de septiembre" in (result.message or "").casefold()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "date"
    assert result.pending_confirmation.expires_at > expiration_before_discovery
    assert gateway.slot_requests == [
        (
            UUID("33333333-3333-3333-3333-333333333333"),
            UUID("44444444-4444-4444-4444-444444444444"),
            date(2026, 9, day),
        )
        for day in range(8, 12)
    ]


@pytest.mark.anyio
async def test_booking_past_date_is_rejected_without_querying_slots() -> None:
    class RecordingSlotsGateway(Gateway):
        def __init__(self) -> None:
            super().__init__()
            self.slot_requests: list[date] = []

        async def list_booking_slots(
            self,
            veterinarian_id: UUID,
            service_id: UUID,
            booking_date: date,
            bearer_token: str,
        ) -> tuple[AppointmentBookingSlot, ...]:
            self.slot_requests.append(booking_date)
            return ()

    gateway = RecordingSlotsGateway()
    executor = AppointmentsModuleExecutor(
        gateway,
        "America/Bogota",
        today_provider=lambda: date(2026, 9, 8),
    )
    result = await executor.execute(
        request("Quiero agendar una cita", "appointments.book"), context()
    )
    for answer in ("1", "1", "1"):
        result = await executor.execute(
            request(answer, "appointments.booking", result.pending_confirmation), context()
        )

    result = await executor.execute(
        request("el 5 de este mes", "appointments.booking", result.pending_confirmation),
        context(),
    )

    assert gateway.slot_requests == []
    assert "ya pasó" in (result.message or "").casefold()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "date"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "expected_error"),
    [
        ("¿Tiene cupo el 31 de febrero?", "fecha no existe"),
        ("¿Tiene cupo el día 15?", "día más específico"),
    ],
)
async def test_booking_structured_date_error_with_availability_words_is_rejected(
    message: str,
    expected_error: str,
) -> None:
    class RecordingSlotsGateway(Gateway):
        def __init__(self) -> None:
            super().__init__()
            self.slot_requests: list[date] = []

        async def list_booking_slots(
            self,
            veterinarian_id: UUID,
            service_id: UUID,
            booking_date: date,
            bearer_token: str,
        ) -> tuple[AppointmentBookingSlot, ...]:
            self.slot_requests.append(booking_date)
            return ()

    gateway = RecordingSlotsGateway()
    executor = AppointmentsModuleExecutor(
        gateway,
        "America/Bogota",
        today_provider=lambda: date(2026, 9, 8),
    )
    result = await executor.execute(
        request("Quiero agendar una cita", "appointments.book"), context()
    )
    for answer in ("1", "1", "1"):
        result = await executor.execute(
            request(answer, "appointments.booking", result.pending_confirmation), context()
        )

    result = await executor.execute(
        request(
            message,
            "appointments.booking",
            result.pending_confirmation,
        ),
        context(),
    )

    assert gateway.slot_requests == []
    assert expected_error in (result.message or "").casefold()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "date"


@pytest.mark.anyio
async def test_booking_no_slots_preserves_selected_veterinarian() -> None:
    class NoSlotsGateway(Gateway):
        async def list_booking_slots(
            self,
            veterinarian_id: UUID,
            service_id: UUID,
            booking_date: date,
            bearer_token: str,
        ) -> tuple[AppointmentBookingSlot, ...]:
            return ()

    executor = AppointmentsModuleExecutor(
        NoSlotsGateway(),
        "America/Bogota",
        today_provider=lambda: date(2026, 9, 8),
    )
    result = await executor.execute(
        request("Quiero agendar una cita", "appointments.book"), context()
    )
    for answer in ("1", "1", "1"):
        result = await executor.execute(
            request(answer, "appointments.booking", result.pending_confirmation), context()
        )

    result = await executor.execute(
        request("mañana", "appointments.booking", result.pending_confirmation), context()
    )

    assert "dra." in (result.message or "").casefold()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["veterinarian_id"] == (
        "33333333-3333-3333-3333-333333333333"
    )
    assert result.pending_confirmation.payload["step"] == "date"


@pytest.mark.anyio
async def test_booking_without_pets_hands_off_to_registration_and_preserves_booking() -> None:
    class GatewayWithoutPets(Gateway):
        async def get_booking_options(self, bearer_token: str) -> AppointmentBookingOptions:
            options = await super().get_booking_options(bearer_token)
            return AppointmentBookingOptions(
                pets=(),
                services=options.services,
                veterinarians=options.veterinarians,
                requires_requester_phone_number=options.requires_requester_phone_number,
            )

    result = await AppointmentsModuleExecutor(GatewayWithoutPets(), "America/Bogota").execute(
        request("Quiero agendar una cita", "appointments.book"), context()
    )

    assert result.pending_confirmation is None
    assert result.handoff is not None
    assert result.handoff.target == ModuleContinuation("pet_profile", "pets.register")
    assert result.handoff.continuation == ModuleContinuation("appointments", "appointments.book")
    assert "registrar" in (result.message or "").casefold()


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
async def test_booking_pending_state_cannot_be_resumed_by_another_account() -> None:
    gateway = Gateway()
    executor = AppointmentsModuleExecutor(gateway, "America/Bogota")
    started = await executor.execute(
        request("Quiero reservar una cita", "appointments.book"), context()
    )

    result = await executor.execute(
        request("1", "appointments.booking", started.pending_confirmation),
        context(UUID("99999999-9999-9999-9999-999999999999")),
    )

    assert "no pertenece a esta cuenta" in (result.message or "")
    assert result.pending_confirmation is None
    assert gateway.created == []


@pytest.mark.anyio
async def test_booking_does_not_shift_a_displayed_slot_when_availability_changes() -> None:
    class ChangingSlotsGateway(Gateway):
        def __init__(self) -> None:
            super().__init__()
            self.slot_call_count = 0

        async def list_booking_slots(
            self,
            veterinarian_id: UUID,
            service_id: UUID,
            booking_date: date,
            bearer_token: str,
        ) -> tuple[AppointmentBookingSlot, ...]:
            self.slot_call_count += 1
            if self.slot_call_count == 1:
                return (
                    AppointmentBookingSlot(
                        SLOT_AVAILABILITY_ID,
                        datetime(2026, 9, 10, 15, tzinfo=UTC),
                        datetime(2026, 9, 10, 15, 30, tzinfo=UTC),
                    ),
                )
            return (
                AppointmentBookingSlot(
                    SLOT_AVAILABILITY_ID,
                    datetime(2026, 9, 10, 16, tzinfo=UTC),
                    datetime(2026, 9, 10, 16, 30, tzinfo=UTC),
                ),
            )

    gateway = ChangingSlotsGateway()
    executor = AppointmentsModuleExecutor(gateway, "America/Bogota")
    result = await executor.execute(
        request("Quiero reservar una cita", "appointments.book"), context()
    )
    for answer in ("1", "1", "1", "10/09/2026"):
        result = await executor.execute(
            request(answer, "appointments.booking", result.pending_confirmation), context()
        )

    result = await executor.execute(
        request("1", "appointments.booking", result.pending_confirmation), context()
    )

    assert "ya no está disponible" in (result.message or "")
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "date"
    assert gateway.created == []


@pytest.mark.anyio
async def test_booking_request_routes_to_appointments_without_llm() -> None:
    command = request("Quiero agendar una cita", "appointments.book").command

    decision = await RuleBasedIntentRouter(APPOINTMENTS_ROUTING_RULES).route(
        command, (APPOINTMENTS_MANIFEST,)
    )

    assert decision.module_id == "appointments"
    assert decision.intent == "appointments.book"


# ---------------------------------------------------------------------------
# Cancel flow
# ---------------------------------------------------------------------------


class GatewayWithCancel(Gateway):
    def __init__(self, items: tuple[AppointmentItem, ...] = (appointment(),)) -> None:
        super().__init__(items)
        self.cancelled: list[tuple[UUID, str, str | None]] = []

    async def cancel_owned(
        self, appointment_id: UUID, bearer_token: str, *, comment: str | None = None
    ) -> None:
        self.cancelled.append((appointment_id, bearer_token, comment))


@pytest.mark.anyio
async def test_cancel_start_with_one_appointment_shows_summary_and_awaits_confirmation() -> None:
    gateway = GatewayWithCancel()
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("Cancelar mi cita", "appointments.cancel"), context()
    )
    assert "Encontré esta cita" in (result.message or "")
    assert "¿Confirmas que deseas cancelarla?" in (result.message or "")
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.action == "appointments.cancel"
    assert gateway.cancelled == []


@pytest.mark.anyio
async def test_cancel_start_with_no_appointments_returns_no_appointments_message() -> None:
    gateway = GatewayWithCancel(())
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("Cancelar mi cita", "appointments.cancel"), context()
    )
    assert "No tienes citas agendadas" in (result.message or "")
    assert result.pending_confirmation is None


@pytest.mark.anyio
async def test_cancel_confirmation_yes_calls_cancel_owned_and_reports_success() -> None:
    gateway = GatewayWithCancel()
    executor = AppointmentsModuleExecutor(gateway, "America/Bogota")
    started = await executor.execute(request("Cancelar mi cita", "appointments.cancel"), context())
    result = await executor.execute(
        request("sí", "appointments.canceling", started.pending_confirmation), context()
    )
    assert "cancelada correctamente" in (result.message or "")
    assert result.pending_confirmation is None
    assert len(gateway.cancelled) == 1
    assert gateway.cancelled[0][0] == UUID("11111111-1111-1111-1111-111111111111")


@pytest.mark.anyio
async def test_cancel_confirmation_no_aborts_without_calling_cancel() -> None:
    gateway = GatewayWithCancel()
    executor = AppointmentsModuleExecutor(gateway, "America/Bogota")
    started = await executor.execute(request("Cancelar mi cita", "appointments.cancel"), context())
    result = await executor.execute(
        request("no", "appointments.canceling", started.pending_confirmation), context()
    )
    assert "no se realizaron cambios" in (result.message or "")
    assert result.pending_confirmation is None
    assert gateway.cancelled == []


@pytest.mark.anyio
async def test_cancel_intent_is_routed_by_rule_based_router() -> None:
    command = request("Cancelar mi cita", "appointments.cancel").command
    decision = await RuleBasedIntentRouter(APPOINTMENTS_ROUTING_RULES).route(
        command, (APPOINTMENTS_MANIFEST,)
    )
    assert decision.module_id == "appointments"
    assert decision.intent == "appointments.cancel"


# ---------------------------------------------------------------------------
# Reschedule flow
# ---------------------------------------------------------------------------


class GatewayWithReschedule(Gateway):
    def __init__(self, items: tuple[AppointmentItem, ...] = (appointment(),)) -> None:
        super().__init__(items)
        self.reschedule_code_calls: list[tuple] = []
        self.reschedule_confirm_calls: list[tuple] = []
        self._fixed_otp_id = UUID("aaaabbbb-aaaa-aaaa-aaaa-aaaaaaaaaaaa")

    async def cancel_owned(
        self, appointment_id: UUID, bearer_token: str, *, comment: str | None = None
    ) -> None:
        raise NotImplementedError

    async def request_reschedule_code(
        self,
        appointment_id: UUID,
        phone: str,
        availability_id: UUID,
        scheduled_start_utc: datetime,
        scheduled_end_utc: datetime,
        bearer_token: str,
    ) -> UUID:
        self.reschedule_code_calls.append(
            (
                appointment_id,
                phone,
                availability_id,
                scheduled_start_utc,
                scheduled_end_utc,
                bearer_token,
            )
        )
        return self._fixed_otp_id

    async def confirm_reschedule_code(
        self,
        appointment_id: UUID,
        phone: str,
        code: str,
        bearer_token: str,
    ) -> None:
        self.reschedule_confirm_calls.append((appointment_id, phone, code, bearer_token))


@pytest.mark.anyio
async def test_reschedule_start_with_one_appointment_asks_for_date() -> None:
    gateway = GatewayWithReschedule()
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("Reprogramar mi cita", "appointments.reschedule"), context()
    )
    assert "Encontré esta cita" in (result.message or "")
    assert (result.message or "").endswith("¿Para qué fecha deseas reprogramar la cita?")
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.action == "appointments.reschedule.collect"


@pytest.mark.anyio
async def test_reschedule_start_with_no_appointments_returns_no_appointments_message() -> None:
    gateway = GatewayWithReschedule(())
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("Reprogramar mi cita", "appointments.reschedule"), context()
    )
    assert "No tienes citas para reprogramar" in (result.message or "")
    assert result.pending_confirmation is None


@pytest.mark.anyio
async def test_reschedule_accepts_legacy_selection_draft_without_veterinarian_name() -> None:
    from app.orchestration.module_executor import PendingConfirmation

    pending = PendingConfirmation.create(
        module_id="appointments",
        action="appointments.reschedule.collect",
        payload={
            "account_id": str(DEFAULT_ACCOUNT_ID),
            "_selecting": True,
            "options": [
                {
                    "id": "11111111-1111-1111-1111-111111111111",
                    "avail_id": "66666666-6666-6666-6666-666666666666",
                    "service_id": "44444444-4444-4444-4444-444444444444",
                    "vet_id": "33333333-3333-3333-3333-333333333333",
                    "label": "Luna — Consulta general",
                }
            ],
        },
        ttl_seconds=600,
        intent="appointments.rescheduling",
    )

    result = await AppointmentsModuleExecutor(
        GatewayWithReschedule(), "America/Bogota"
    ).execute(request("1", "appointments.rescheduling", pending), context())

    assert result.message == "¿Para qué fecha deseas reprogramar la cita?"
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "date"
    assert result.pending_confirmation.payload["veterinarian_id"] == (
        "33333333-3333-3333-3333-333333333333"
    )
    assert "veterinarian_name" not in result.pending_confirmation.payload


@pytest.mark.anyio
async def test_reschedule_date_step_shows_available_slots() -> None:
    from app.modules.appointments.contracts_booking import AppointmentRescheduleDraft
    from app.orchestration.module_executor import PendingConfirmation

    draft = AppointmentRescheduleDraft(
        account_id=str(DEFAULT_ACCOUNT_ID),
        appointment_id="11111111-1111-1111-1111-111111111111",
        availability_id="66666666-6666-6666-6666-666666666666",
        appointment_summary="Luna — Consulta general",
        step="date",
        service_id="44444444-4444-4444-4444-444444444444",
        veterinarian_id="33333333-3333-3333-3333-333333333333",
    )
    pending = PendingConfirmation.create(
        module_id="appointments",
        action="appointments.reschedule.collect",
        payload=draft.to_payload(),
        ttl_seconds=600,
        intent="appointments.rescheduling",
    )
    gateway = GatewayWithReschedule()
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("10/09/2026", "appointments.rescheduling", pending), context()
    )
    assert "Horarios disponibles" in (result.message or "")
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload.get("step") == "slot"


@pytest.mark.anyio
async def test_reschedule_natural_date_queries_original_veterinarian_availability() -> None:
    class RecordingRescheduleGateway(GatewayWithReschedule):
        def __init__(self) -> None:
            super().__init__()
            self.slot_requests: list[tuple[UUID, UUID, date]] = []

        async def list_booking_slots(
            self,
            veterinarian_id: UUID,
            service_id: UUID,
            booking_date: date,
            bearer_token: str,
        ) -> tuple[AppointmentBookingSlot, ...]:
            self.slot_requests.append((veterinarian_id, service_id, booking_date))
            return (
                AppointmentBookingSlot(
                    SLOT_AVAILABILITY_ID,
                    datetime(2026, 9, 9, 15, tzinfo=UTC),
                    datetime(2026, 9, 9, 15, 30, tzinfo=UTC),
                ),
            )

    gateway = RecordingRescheduleGateway()
    executor = AppointmentsModuleExecutor(
        gateway,
        "America/Bogota",
        today_provider=lambda: date(2026, 9, 8),
    )
    started = await executor.execute(
        request("Reprogramar mi cita", "appointments.reschedule"), context()
    )

    result = await executor.execute(
        request("mañana", "appointments.rescheduling", started.pending_confirmation), context()
    )

    assert gateway.slot_requests == [
        (
            UUID("33333333-3333-3333-3333-333333333333"),
            UUID("44444444-4444-4444-4444-444444444444"),
            date(2026, 9, 9),
        )
    ]
    assert "horarios disponibles" in (result.message or "").casefold()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "slot"


@pytest.mark.anyio
async def test_reschedule_availability_discovery_uses_original_selection() -> None:
    class DiscoveryGateway(GatewayWithReschedule):
        def __init__(self) -> None:
            super().__init__()
            self.slot_requests: list[tuple[UUID, UUID, date]] = []

        async def list_booking_slots(
            self,
            veterinarian_id: UUID,
            service_id: UUID,
            booking_date: date,
            bearer_token: str,
        ) -> tuple[AppointmentBookingSlot, ...]:
            self.slot_requests.append((veterinarian_id, service_id, booking_date))
            if booking_date != date(2026, 9, 10):
                return ()
            return (
                AppointmentBookingSlot(
                    SLOT_AVAILABILITY_ID,
                    datetime(2026, 9, 10, 15, tzinfo=UTC),
                    datetime(2026, 9, 10, 15, 30, tzinfo=UTC),
                ),
            )

    gateway = DiscoveryGateway()
    executor = AppointmentsModuleExecutor(
        gateway,
        "America/Bogota",
        today_provider=lambda: date(2026, 9, 8),
        availability_search_days=4,
        availability_max_dates=3,
    )
    started = await executor.execute(
        request("Reprogramar mi cita", "appointments.reschedule"), context()
    )

    result = await executor.execute(
        request(
            "¿Cuándo tiene cupo?",
            "appointments.rescheduling",
            started.pending_confirmation,
        ),
        context(),
    )

    assert "jueves 10 de septiembre" in (result.message or "").casefold()
    assert "dra. ana" in (result.message or "").casefold()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "date"
    assert gateway.slot_requests == [
        (
            UUID("33333333-3333-3333-3333-333333333333"),
            UUID("44444444-4444-4444-4444-444444444444"),
            date(2026, 9, day),
        )
        for day in range(8, 12)
    ]


@pytest.mark.anyio
async def test_reschedule_natural_past_date_is_rejected_without_querying_slots() -> None:
    class RecordingRescheduleGateway(GatewayWithReschedule):
        def __init__(self) -> None:
            super().__init__()
            self.slot_requests: list[date] = []

        async def list_booking_slots(
            self,
            veterinarian_id: UUID,
            service_id: UUID,
            booking_date: date,
            bearer_token: str,
        ) -> tuple[AppointmentBookingSlot, ...]:
            self.slot_requests.append(booking_date)
            return ()

    gateway = RecordingRescheduleGateway()
    executor = AppointmentsModuleExecutor(
        gateway,
        "America/Bogota",
        today_provider=lambda: date(2026, 9, 8),
    )
    started = await executor.execute(
        request("Reprogramar mi cita", "appointments.reschedule"), context()
    )

    result = await executor.execute(
        request(
            "el 5 de este mes",
            "appointments.rescheduling",
            started.pending_confirmation,
        ),
        context(),
    )

    assert gateway.slot_requests == []
    assert "ya pasó" in (result.message or "").casefold()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "date"


@pytest.mark.anyio
async def test_reschedule_past_date_with_availability_words_is_rejected() -> None:
    class RecordingRescheduleGateway(GatewayWithReschedule):
        def __init__(self) -> None:
            super().__init__()
            self.slot_requests: list[date] = []

        async def list_booking_slots(
            self,
            veterinarian_id: UUID,
            service_id: UUID,
            booking_date: date,
            bearer_token: str,
        ) -> tuple[AppointmentBookingSlot, ...]:
            self.slot_requests.append(booking_date)
            return ()

    gateway = RecordingRescheduleGateway()
    executor = AppointmentsModuleExecutor(
        gateway,
        "America/Bogota",
        today_provider=lambda: date(2026, 9, 8),
    )
    started = await executor.execute(
        request("Reprogramar mi cita", "appointments.reschedule"), context()
    )

    result = await executor.execute(
        request(
            "¿Cuándo tiene cupo el 5 de este mes?",
            "appointments.rescheduling",
            started.pending_confirmation,
        ),
        context(),
    )

    assert gateway.slot_requests == []
    assert "ya pasó" in (result.message or "").casefold()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "date"


@pytest.mark.anyio
async def test_reschedule_slot_step_asks_for_phone() -> None:
    from app.modules.appointments.contracts_booking import AppointmentRescheduleDraft
    from app.orchestration.module_executor import PendingConfirmation

    draft = AppointmentRescheduleDraft(
        account_id=str(DEFAULT_ACCOUNT_ID),
        appointment_id="11111111-1111-1111-1111-111111111111",
        availability_id="66666666-6666-6666-6666-666666666666",
        appointment_summary="Luna — Consulta general",
        step="slot",
        service_id="44444444-4444-4444-4444-444444444444",
        veterinarian_id="33333333-3333-3333-3333-333333333333",
        booking_date="2026-09-10",
        advertised_slot_starts_utc=("2026-09-10 15:00:00+00:00",),
    )
    payload = draft.to_payload()
    payload["advertised_slot_ends_utc"] = ["2026-09-10 15:30:00+00:00"]
    pending = PendingConfirmation.create(
        module_id="appointments",
        action="appointments.reschedule.collect",
        payload=payload,
        ttl_seconds=600,
        intent="appointments.rescheduling",
    )
    gateway = GatewayWithReschedule()
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("1", "appointments.rescheduling", pending), context()
    )
    assert "teléfono" in (result.message or "").lower()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload.get("step") == "phone"
    assert result.pending_confirmation.payload.get("new_availability_id") == str(
        SLOT_AVAILABILITY_ID
    )


@pytest.mark.anyio
async def test_reschedule_phone_step_sends_otp_and_awaits_code() -> None:
    from app.modules.appointments.contracts_booking import AppointmentRescheduleDraft
    from app.orchestration.module_executor import PendingConfirmation

    draft = AppointmentRescheduleDraft(
        account_id=str(DEFAULT_ACCOUNT_ID),
        appointment_id="11111111-1111-1111-1111-111111111111",
        availability_id="66666666-6666-6666-6666-666666666666",
        appointment_summary="Luna — Consulta general",
        step="phone",
        service_id="44444444-4444-4444-4444-444444444444",
        veterinarian_id="33333333-3333-3333-3333-333333333333",
        booking_date="2026-09-10",
        new_availability_id=str(SLOT_AVAILABILITY_ID),
        new_scheduled_start_utc="2026-09-10T15:00:00+00:00",
        new_scheduled_end_utc="2026-09-10T15:30:00+00:00",
    )
    pending = PendingConfirmation.create(
        module_id="appointments",
        action="appointments.reschedule.collect",
        payload=draft.to_payload(),
        ttl_seconds=600,
        intent="appointments.rescheduling",
    )
    gateway = GatewayWithReschedule()
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("3001234567", "appointments.rescheduling", pending), context()
    )
    assert "código" in (result.message or "").lower()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.action == "appointments.reschedule.otp"
    assert len(gateway.reschedule_code_calls) == 1
    assert gateway.reschedule_code_calls[0][2] == SLOT_AVAILABILITY_ID


@pytest.mark.anyio
async def test_reschedule_otp_step_confirms_and_reports_success() -> None:
    from app.modules.appointments.contracts_booking import AppointmentRescheduleDraft
    from app.orchestration.module_executor import PendingConfirmation

    draft = AppointmentRescheduleDraft(
        account_id=str(DEFAULT_ACCOUNT_ID),
        appointment_id="11111111-1111-1111-1111-111111111111",
        availability_id="66666666-6666-6666-6666-666666666666",
        appointment_summary="Luna — Consulta general",
        step="otp_sent",
        service_id="44444444-4444-4444-4444-444444444444",
        veterinarian_id="33333333-3333-3333-3333-333333333333",
        booking_date="2026-09-10",
        new_scheduled_start_utc="2026-09-10T15:00:00+00:00",
        new_scheduled_end_utc="2026-09-10T15:30:00+00:00",
        requester_phone="3001234567",
    )
    pending = PendingConfirmation.create(
        module_id="appointments",
        action="appointments.reschedule.otp",
        payload=draft.to_payload(),
        ttl_seconds=600,
        intent="appointments.rescheduling",
    )
    gateway = GatewayWithReschedule()
    result = await AppointmentsModuleExecutor(gateway, "America/Bogota").execute(
        request("123456", "appointments.rescheduling", pending), context()
    )
    assert "reprogramada correctamente" in (result.message or "")
    assert result.pending_confirmation is None
    assert len(gateway.reschedule_confirm_calls) == 1
    assert gateway.reschedule_confirm_calls[0][2] == "123456"


@pytest.mark.anyio
async def test_reschedule_intent_is_routed_by_rule_based_router() -> None:
    command = request("Reprogramar mi cita", "appointments.reschedule").command
    decision = await RuleBasedIntentRouter(APPOINTMENTS_ROUTING_RULES).route(
        command, (APPOINTMENTS_MANIFEST,)
    )
    assert decision.module_id == "appointments"
    assert decision.intent == "appointments.reschedule"


@pytest.mark.anyio
@pytest.mark.parametrize(
    "message",
    (
        "necesito cambiar una cita es que se me presentó un inconveniente",
        "quiero cambiar la cita",
        "necesito mover una cita",
        "deseo reagendar una cita",
        "quiero reprogramar la cita",
        "cambiar el horario de la cita",
        "cambiar la fecha de una cita",
    ),
)
async def test_natural_reschedule_requests_route_without_llm(message: str) -> None:
    command = request(message, "appointments.reschedule").command
    decision = await RuleBasedIntentRouter(APPOINTMENTS_ROUTING_RULES).route(
        command, (APPOINTMENTS_MANIFEST,)
    )

    assert decision.module_id == "appointments"
    assert decision.intent == "appointments.reschedule"


@pytest.mark.anyio
async def test_unrelated_change_request_does_not_route_to_reschedule() -> None:
    command = request("quiero cambiar de tema", "appointments.reschedule").command
    decision = await RuleBasedIntentRouter(APPOINTMENTS_ROUTING_RULES).route(
        command, (APPOINTMENTS_MANIFEST,)
    )

    assert decision.module_id is None
    assert decision.intent is None
