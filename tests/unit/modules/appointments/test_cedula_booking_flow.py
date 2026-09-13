from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest

from app.modules.appointments.graph import AppointmentsModuleExecutor
from app.modules.appointments.services.owner_contact import (
    parse_identification_number,
    parse_owner_email,
    parse_owner_full_name,
)
from app.orchestration.guest_access import FEATURE_IN_DEVELOPMENT, GUEST_SYSTEM_PROMPT
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_executor import PendingConfirmation
from app.orchestration.response_builder import build_guest_link_required_result
from tests.unit.modules.appointments.test_appointments_module import (
    Gateway,
    context,
    request,
)


def test_parses_owner_contact_fields() -> None:
    assert parse_identification_number("1.234.567") == "1234567"
    assert parse_owner_full_name("Ana Pérez") == "Ana Pérez"
    assert parse_owner_email("Ana@Example.COM") == "ana@example.com"
    assert parse_identification_number("123") is None
    assert parse_owner_email("no-es-correo") is None


def test_guest_prompt_avoids_advisor_and_vincular() -> None:
    assert "/vincular" not in GUEST_SYSTEM_PROMPT
    assert "asesor" not in GUEST_SYSTEM_PROMPT.casefold()
    assert FEATURE_IN_DEVELOPMENT in GUEST_SYSTEM_PROMPT


def test_guest_private_feature_message_is_in_development() -> None:
    result = build_guest_link_required_result(
        MessageCommand(
            message="historial clínico",
            conversation_id=UUID("10000000-0000-0000-0000-000000000001"),
            user_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            pet_id=None,
            channel="telegram",
            language="es-CO",
            roles=("TelegramGuest",),
            is_escalated=False,
            correlation_id=UUID("ffffffff-ffff-ffff-ffff-ffffffffffff"),
            idempotency_key="guest-1",
            publish_as_global_knowledge=False,
        )
    )
    assert result.message == FEATURE_IN_DEVELOPMENT
    assert result.access_requirement.value == "none"


@pytest.mark.anyio
async def test_booking_starts_by_asking_for_cedula() -> None:
    executor = AppointmentsModuleExecutor(Gateway(), "America/Bogota", booking_ttl_seconds=300)
    result = await executor.execute(request("quiero agendar", "appointments.book"), context())
    assert "cédula" in (result.message or "").casefold()
    assert result.pending_confirmation is not None
    assert result.pending_confirmation.payload["step"] == "identification"


@pytest.mark.anyio
async def test_booking_collects_contact_then_pets() -> None:
    gateway = Gateway()
    executor = AppointmentsModuleExecutor(gateway, "America/Bogota", booking_ttl_seconds=300)
    started = await executor.execute(request("agendar", "appointments.book"), context())
    pending = started.pending_confirmation
    assert pending is not None

    for message, expected in (
        ("1234567890", "nombre"),
        ("Ana Pérez", "correo"),
    ):
        step = await executor.execute(
            request(message, "appointments.booking", pending=pending), context()
        )
        assert expected in (step.message or "").casefold()
        pending = step.pending_confirmation
        assert pending is not None

    pets = await executor.execute(
        request("ana@example.com", "appointments.booking", pending=pending), context()
    )
    assert gateway.find_or_create_calls
    assert "mascota" in (pets.message or "").casefold()
    assert pets.pending_confirmation is not None
    assert pets.pending_confirmation.payload["identification_number"] == "1234567890"


@pytest.mark.anyio
async def test_cancel_asks_for_cedula_then_cancels() -> None:
    gateway = Gateway()
    executor = AppointmentsModuleExecutor(gateway, "America/Bogota", booking_ttl_seconds=300)
    started = await executor.execute(request("cancelar cita", "appointments.cancel"), context())
    assert "cédula" in (started.message or "").casefold()
    pending = started.pending_confirmation
    assert pending is not None

    listed = await executor.execute(
        request("1234567890", "appointments.canceling", pending=pending), context()
    )
    assert "confirmas" in (listed.message or "").casefold()
    pending = listed.pending_confirmation
    assert pending is not None

    done = await executor.execute(
        request("sí", "appointments.canceling", pending=pending), context()
    )
    assert "cancelada" in (done.message or "").casefold()
    assert gateway.cancelled_by_identification == [
        (UUID("11111111-1111-1111-1111-111111111111"), "1234567890")
    ]


@pytest.mark.anyio
async def test_booking_expires_after_idle_ttl() -> None:
    executor = AppointmentsModuleExecutor(Gateway(), "America/Bogota", booking_ttl_seconds=300)
    started = await executor.execute(request("agendar", "appointments.book"), context())
    pending = started.pending_confirmation
    assert pending is not None
    expired = PendingConfirmation(
        module_id=pending.module_id,
        action=pending.action,
        payload=pending.payload,
        expires_at=datetime.now(UTC) - timedelta(seconds=1),
        intent=pending.intent,
    )
    result = await executor.execute(
        request("1234567890", "appointments.booking", pending=expired), context()
    )
    assert "venció" in (result.message or "").casefold()
    assert result.pending_confirmation is None
