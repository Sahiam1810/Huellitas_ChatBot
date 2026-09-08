import json
from datetime import UTC, date, datetime
from uuid import UUID

import httpx
import pytest

from app.adapters.dotnet.appointments import DotNetAppointmentsGateway
from app.ports.appointments_gateway import (
    AppointmentBookingRequest,
    AppointmentNotFoundError,
    AppointmentsAuthenticationError,
    AppointmentsConflictError,
    AppointmentScope,
    AppointmentsForbiddenError,
    AppointmentsInvalidResponseError,
    AppointmentsRequestError,
    AppointmentsUnavailableError,
)


def payload() -> dict[str, object]:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "clientPetId": "22222222-2222-2222-2222-222222222222",
        "petName": "Luna",
        "veterinarianId": "33333333-3333-3333-3333-333333333333",
        "veterinarianName": "Dra. Ana",
        "serviceId": "44444444-4444-4444-4444-444444444444",
        "serviceName": "Consulta general",
        "statusId": "55555555-5555-5555-5555-555555555555",
        "statusName": "AGENDADA",
        "availabilityId": "66666666-6666-6666-6666-666666666666",
        "scheduledStart": "2026-09-03T15:00:00Z",
        "scheduledEnd": "2026-09-03T15:30:00+00:00",
        "notes": "Control",
        "requesterPhoneNumber": "3000000000",
    }


@pytest.mark.anyio
async def test_list_owned_sends_scope_and_parses_contract_without_phone() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/bot/appointments"
        assert request.url.params["scope"] == "upcoming"
        assert request.headers["Authorization"] == "Bearer token"
        return httpx.Response(200, json=[payload()])

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    item = (await gateway.list_owned(AppointmentScope.UPCOMING, "token"))[0]
    assert item.pet_name == "Luna"
    assert item.scheduled_start.tzinfo is UTC
    assert not hasattr(item, "requester_phone_number")


@pytest.mark.anyio
async def test_get_owned_uses_owned_detail_route() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/bot/appointments/11111111-1111-1111-1111-111111111111"
        return httpx.Response(200, json=payload())

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    item = await gateway.get_owned(UUID(str(payload()["id"])), "token")
    assert item.service_name == "Consulta general"


@pytest.mark.anyio
async def test_get_booking_options_parses_owned_catalog() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/bot/appointments/booking/options"
        assert request.headers["Authorization"] == "Bearer token"
        return httpx.Response(
            200,
            json={
                "pets": [{"id": "22222222-2222-2222-2222-222222222222", "name": "Luna"}],
                "services": [
                    {
                        "id": "44444444-4444-4444-4444-444444444444",
                        "name": "Consulta general",
                        "durationMinutes": 30,
                    }
                ],
                "veterinarians": [
                    {
                        "id": "33333333-3333-3333-3333-333333333333",
                        "fullName": "Dra. Ana",
                        "specialtyName": "Medicina general",
                    }
                ],
                "requiresRequesterPhoneNumber": True,
            },
        )

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    options = await gateway.get_booking_options("token")

    assert options.pets[0].name == "Luna"
    assert options.services[0].duration_minutes == 30
    assert options.veterinarians[0].specialty_name == "Medicina general"
    assert options.requires_requester_phone_number is True


@pytest.mark.anyio
async def test_list_booking_slots_sends_iso_date_and_parses_utc() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/bot/appointments/booking/slots"
        assert request.url.params["date"] == "2026-09-10"
        return httpx.Response(
            200,
            json=[
                {
                    "availabilityId": "77777777-7777-7777-7777-777777777777",
                    "scheduledStartUtc": "2026-09-10T15:00:00Z",
                    "scheduledEndUtc": "2026-09-10T15:30:00Z",
                }
            ],
        )

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    slots = await gateway.list_booking_slots(
        UUID("33333333-3333-3333-3333-333333333333"),
        UUID("44444444-4444-4444-4444-444444444444"),
        date(2026, 9, 10),
        "token",
    )

    assert slots[0].scheduled_start_utc == datetime(2026, 9, 10, 15, tzinfo=UTC)
    assert slots[0].availability_id == UUID("77777777-7777-7777-7777-777777777777")


@pytest.mark.anyio
async def test_create_owned_sends_idempotency_header_and_minimal_body() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/bot/appointments"
        assert request.headers["Idempotency-Key"] == "message-001"
        body = json.loads(request.content)
        assert set(body) == {
            "petId",
            "veterinarianId",
            "serviceId",
            "scheduledStartUtc",
            "notes",
            "requesterPhoneNumber",
        }
        return httpx.Response(201, json=payload())

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    booking = AppointmentBookingRequest(
        pet_id=UUID("22222222-2222-2222-2222-222222222222"),
        veterinarian_id=UUID("33333333-3333-3333-3333-333333333333"),
        service_id=UUID("44444444-4444-4444-4444-444444444444"),
        scheduled_start_utc=datetime(2026, 9, 3, 15, tzinfo=UTC),
        notes="Control",
        requester_phone_number="3000000000",
    )

    created = await gateway.create_owned(booking, "message-001", "token")

    assert created.id == UUID("11111111-1111-1111-1111-111111111111")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, AppointmentsAuthenticationError),
        (403, AppointmentsForbiddenError),
        (404, AppointmentNotFoundError),
        (422, AppointmentsRequestError),
        (503, AppointmentsUnavailableError),
    ],
)
async def test_maps_safe_backend_errors(status: int, error: type[Exception]) -> None:
    gateway = DotNetAppointmentsGateway(
        "https://backend.test",
        2,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(status, text="secret"))
        ),
    )
    with pytest.raises(error) as captured:
        await gateway.list_owned(AppointmentScope.ALL, "token")
    assert "secret" not in str(captured.value)


@pytest.mark.anyio
@pytest.mark.parametrize(
    "bad", [{"x": 1}, [{**payload(), "scheduledStart": "2026-09-03T15:00:00"}]]
)
async def test_rejects_malformed_contract(bad: object) -> None:
    gateway = DotNetAppointmentsGateway(
        "https://backend.test",
        2,
        client=httpx.AsyncClient(
            transport=httpx.MockTransport(lambda _: httpx.Response(200, json=bad))
        ),
    )
    with pytest.raises(AppointmentsInvalidResponseError):
        await gateway.list_owned(AppointmentScope.ALL, "token")


# ── Tests cancel_owned & reschedule_code ───────────────────────────────────

@pytest.mark.anyio
async def test_cancel_owned_sends_patch_with_jwt() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        assert request.url.path == (
            "/api/bot/appointments/11111111-1111-1111-1111-111111111111/cancel"
        )
        assert request.headers["Authorization"] == "Bearer token"
        body = json.loads(request.content)
        assert body.get("comment") == "Cliente solicita cancelar."
        return httpx.Response(204)

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    await gateway.cancel_owned(
        UUID("11111111-1111-1111-1111-111111111111"),
        "token",
        comment="Cliente solicita cancelar.",
    )


@pytest.mark.anyio
async def test_cancel_owned_raises_conflict_on_409() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409)

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(AppointmentsConflictError):
        await gateway.cancel_owned(UUID("11111111-1111-1111-1111-111111111111"), "token")


@pytest.mark.anyio
async def test_cancel_owned_raises_forbidden_on_403() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(AppointmentsForbiddenError):
        await gateway.cancel_owned(UUID("11111111-1111-1111-1111-111111111111"), "token")


@pytest.mark.anyio
async def test_request_reschedule_code_sends_post_and_returns_session_id() -> None:
    session_id = "aaaaaaaa-0000-0000-0000-000000000001"

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == (
            "/api/appointments/mine/11111111-1111-1111-1111-111111111111/request-code"
        )
        body = json.loads(request.content)
        assert body["phoneNumber"] == "3001234567"
        assert body["action"] == "Reschedule"
        reschedule = body["reschedule"]
        assert reschedule["availabilityId"] == "66666666-6666-6666-6666-666666666666"
        assert reschedule["scheduledStart"] == "2026-09-10T15:00:00Z"
        assert reschedule["scheduledEnd"] == "2026-09-10T15:30:00Z"
        return httpx.Response(202, json={"sessionId": session_id})

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    result = await gateway.request_reschedule_code(
        appointment_id=UUID("11111111-1111-1111-1111-111111111111"),
        phone="3001234567",
        availability_id=UUID("66666666-6666-6666-6666-666666666666"),
        scheduled_start_utc=datetime(2026, 9, 10, 15, 0, tzinfo=UTC),
        scheduled_end_utc=datetime(2026, 9, 10, 15, 30, tzinfo=UTC),
        bearer_token="token",
    )
    assert result == UUID(session_id)


@pytest.mark.anyio
async def test_request_reschedule_code_raises_conflict_on_409() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409)

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(AppointmentsConflictError):
        await gateway.request_reschedule_code(
            UUID("11111111-1111-1111-1111-111111111111"),
            "3001234567",
            UUID("66666666-6666-6666-6666-666666666666"),
            datetime(2026, 9, 10, 15, 0, tzinfo=UTC),
            datetime(2026, 9, 10, 15, 30, tzinfo=UTC),
            "token",
        )


@pytest.mark.anyio
async def test_confirm_reschedule_code_sends_post_and_returns_none() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == (
            "/api/appointments/mine/11111111-1111-1111-1111-111111111111/confirm-code"
        )
        body = json.loads(request.content)
        assert body["phoneNumber"] == "3001234567"
        assert body["code"] == "123456"
        assert body["action"] == "Reschedule"
        return httpx.Response(204)

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    await gateway.confirm_reschedule_code(
        UUID("11111111-1111-1111-1111-111111111111"),
        "3001234567",
        "123456",
        "token",
    )


@pytest.mark.anyio
async def test_confirm_reschedule_code_raises_unauthorized_on_401() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401)

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(AppointmentsAuthenticationError):
        await gateway.confirm_reschedule_code(
            UUID("11111111-1111-1111-1111-111111111111"), "3001234567", "000000", "token"
        )
