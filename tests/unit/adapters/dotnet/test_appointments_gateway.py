from datetime import UTC
from uuid import UUID

import httpx
import pytest

from app.adapters.dotnet.appointments import DotNetAppointmentsGateway
from app.ports.appointments_gateway import (
    AppointmentNotFoundError,
    AppointmentsAuthenticationError,
    AppointmentScope,
    AppointmentsForbiddenError,
    AppointmentsInvalidResponseError,
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
        assert request.url.path == "/api/appointments/mine"
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
        assert request.url.path.endswith("/11111111-1111-1111-1111-111111111111")
        return httpx.Response(200, json=payload())

    gateway = DotNetAppointmentsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    item = await gateway.get_owned(UUID(str(payload()["id"])), "token")
    assert item.service_name == "Consulta general"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "error"),
    [
        (401, AppointmentsAuthenticationError),
        (403, AppointmentsForbiddenError),
        (404, AppointmentNotFoundError),
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
