from uuid import UUID

import pytest

from app.orchestration.guest_identification import (
    GUEST_IDENTIFICATION_ACTION,
    GuestIdentificationCoordinator,
    parse_guest_identification,
)
from app.orchestration.module_executor import PendingConfirmation
from app.ports.guest_identity_gateway import (
    GuestClientMatch,
    GuestIdentityConflictError,
    GuestOwnerRegistration,
)

PERSON_ID = UUID("11111111-1111-1111-1111-111111111111")
CLIENT_ID = UUID("22222222-2222-2222-2222-222222222222")
NEW_PERSON_ID = UUID("33333333-3333-3333-3333-333333333333")
NEW_CLIENT_ID = UUID("44444444-4444-4444-4444-444444444444")


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def test_parses_the_labeled_multiline_format_from_the_prompt() -> None:
    message = (
        "Nombre: Ana Perez\n"
        "Cédula: 123456789\n"
        "Correo: ana@example.test\n"
        "Teléfono: 3001234567"
    )

    parsed = parse_guest_identification(message)

    assert parsed is not None
    assert parsed.full_name == "Ana Perez"
    assert parsed.identification_number == "123456789"
    assert parsed.email == "ana@example.test"
    assert parsed.phone_number == "3001234567"


def test_parses_a_comma_separated_message_without_labels() -> None:
    message = "Ana Perez, 123456789, ana@example.test, 3001234567"

    parsed = parse_guest_identification(message)

    assert parsed is not None
    assert parsed.full_name == "Ana Perez"
    assert parsed.identification_number == "123456789"
    assert parsed.phone_number == "3001234567"


def test_returns_none_when_the_email_is_missing() -> None:
    assert parse_guest_identification("Ana Perez, 123456789, 3001234567") is None


def test_returns_none_when_a_field_is_missing_even_with_labels() -> None:
    message = "Nombre: Ana Perez\nCédula: 123456789\nCorreo: ana@example.test"

    assert parse_guest_identification(message) is None


def test_returns_none_for_an_implausible_identification_number() -> None:
    message = "Nombre: Ana Perez\nCédula: 12\nCorreo: ana@example.test\nTeléfono: 3001234567"

    assert parse_guest_identification(message) is None


# ---------------------------------------------------------------------------
# Coordinator
# ---------------------------------------------------------------------------


class FakeGuestIdentityGateway:
    def __init__(
        self,
        *,
        existing: GuestClientMatch | None = None,
        register_conflict: GuestIdentityConflictError | None = None,
        register_result: GuestClientMatch | None = None,
    ) -> None:
        self.existing = existing
        self.register_conflict = register_conflict
        self.register_result = register_result
        self.lookup_calls: list[tuple[str, str]] = []
        self.register_calls: list[tuple[GuestOwnerRegistration, str]] = []
        self.link_calls: list[tuple[UUID, str]] = []

    async def lookup_by_identification(
        self, identification_number: str, bearer_token: str
    ) -> GuestClientMatch | None:
        self.lookup_calls.append((identification_number, bearer_token))
        if len(self.lookup_calls) > 1 and self.register_conflict is not None:
            return self.register_result
        return self.existing

    async def register(
        self, registration: GuestOwnerRegistration, bearer_token: str
    ) -> GuestClientMatch:
        self.register_calls.append((registration, bearer_token))
        if self.register_conflict is not None:
            raise self.register_conflict
        assert self.register_result is not None
        return self.register_result

    async def link_telegram_account(self, person_id: UUID, bearer_token: str) -> None:
        self.link_calls.append((person_id, bearer_token))

    async def close(self) -> None:
        pass


def valid_message() -> str:
    return (
        "Nombre: Ana Perez\n"
        "Cédula: 123456789\n"
        "Correo: ana@example.test\n"
        "Teléfono: 3001234567"
    )


@pytest.mark.anyio
async def test_first_turn_asks_for_the_four_fields_and_sets_a_pending_confirmation() -> None:
    gateway = FakeGuestIdentityGateway()
    coordinator = GuestIdentificationCoordinator(gateway)

    result = await coordinator.handle(
        module_id="appointments",
        intent="appointments.book",
        message="quiero agendar una cita",
        bearer_token="guest-token",
        pending=None,
    )

    assert result.pending_confirmation is not None
    assert result.pending_confirmation.action == GUEST_IDENTIFICATION_ACTION
    assert result.pending_confirmation.module_id == "appointments"
    assert result.pending_confirmation.intent == "appointments.book"
    assert "Nombre" in (result.message or "")
    assert gateway.lookup_calls == []


@pytest.mark.anyio
async def test_existing_client_skips_registration_but_still_links_idempotently() -> None:
    gateway = FakeGuestIdentityGateway(
        existing=GuestClientMatch(person_id=PERSON_ID, client_id=CLIENT_ID)
    )
    coordinator = GuestIdentificationCoordinator(gateway)
    pending = PendingConfirmation.create(
        module_id="appointments",
        action=GUEST_IDENTIFICATION_ACTION,
        payload={},
        ttl_seconds=600,
        intent="appointments.book",
    )

    result = await coordinator.handle(
        module_id="appointments",
        intent="appointments.book",
        message=valid_message(),
        bearer_token="guest-token",
        pending=pending,
    )

    assert gateway.register_calls == []
    assert gateway.link_calls == [(PERSON_ID, "guest-token")]
    assert result.pending_confirmation is None
    assert "Ana" in (result.message or "")


@pytest.mark.anyio
async def test_new_client_registers_and_links() -> None:
    gateway = FakeGuestIdentityGateway(
        existing=None,
        register_result=GuestClientMatch(person_id=NEW_PERSON_ID, client_id=NEW_CLIENT_ID),
    )
    coordinator = GuestIdentificationCoordinator(gateway)
    pending = PendingConfirmation.create(
        module_id="pet_profile",
        action=GUEST_IDENTIFICATION_ACTION,
        payload={},
        ttl_seconds=600,
        intent="pets.register",
    )

    result = await coordinator.handle(
        module_id="pet_profile",
        intent="pets.register",
        message=valid_message(),
        bearer_token="guest-token",
        pending=pending,
    )

    assert len(gateway.register_calls) == 1
    registration, token = gateway.register_calls[0]
    assert registration.identification_number == "123456789"
    assert token == "guest-token"
    assert gateway.link_calls == [(NEW_PERSON_ID, "guest-token")]
    assert result.pending_confirmation is None


@pytest.mark.anyio
async def test_registration_race_falls_back_to_a_second_lookup_and_never_shows_the_raw_error() -> (
    None
):
    gateway = FakeGuestIdentityGateway(
        existing=None,
        register_conflict=GuestIdentityConflictError(
            "Authentication.IdentificationNumberAlreadyExists"
        ),
        register_result=GuestClientMatch(person_id=PERSON_ID, client_id=CLIENT_ID),
    )
    coordinator = GuestIdentificationCoordinator(gateway)
    pending = PendingConfirmation.create(
        module_id="appointments",
        action=GUEST_IDENTIFICATION_ACTION,
        payload={},
        ttl_seconds=600,
        intent="appointments.book",
    )

    result = await coordinator.handle(
        module_id="appointments",
        intent="appointments.book",
        message=valid_message(),
        bearer_token="guest-token",
        pending=pending,
    )

    assert len(gateway.register_calls) == 1
    assert len(gateway.lookup_calls) == 2
    assert gateway.link_calls == [(PERSON_ID, "guest-token")]
    assert result.pending_confirmation is None
    assert "Authentication." not in (result.message or "")


@pytest.mark.anyio
async def test_unparseable_reply_reprompts_and_keeps_the_pending_confirmation() -> None:
    gateway = FakeGuestIdentityGateway()
    coordinator = GuestIdentificationCoordinator(gateway)
    pending = PendingConfirmation.create(
        module_id="appointments",
        action=GUEST_IDENTIFICATION_ACTION,
        payload={},
        ttl_seconds=600,
        intent="appointments.book",
    )

    result = await coordinator.handle(
        module_id="appointments",
        intent="appointments.book",
        message="no entendí qué datos quieres",
        bearer_token="guest-token",
        pending=pending,
    )

    assert result.pending_confirmation == pending
    assert gateway.lookup_calls == []
    assert "Nombre" in (result.message or "")


@pytest.mark.anyio
async def test_email_conflict_reprompts_without_linking() -> None:
    gateway = FakeGuestIdentityGateway(
        existing=None,
        register_conflict=GuestIdentityConflictError("Authentication.UserAlreadyExists"),
    )
    coordinator = GuestIdentificationCoordinator(gateway)
    pending = PendingConfirmation.create(
        module_id="appointments",
        action=GUEST_IDENTIFICATION_ACTION,
        payload={},
        ttl_seconds=600,
        intent="appointments.book",
    )

    result = await coordinator.handle(
        module_id="appointments",
        intent="appointments.book",
        message=valid_message(),
        bearer_token="guest-token",
        pending=pending,
    )

    assert gateway.link_calls == []
    assert result.pending_confirmation is not None
    assert "correo" in (result.message or "").casefold()
