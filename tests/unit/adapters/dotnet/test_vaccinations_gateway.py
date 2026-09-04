import json
from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from app.adapters.dotnet.vaccinations import DotNetVaccinationsGateway
from app.ports.vaccinations_gateway import (
    VaccinationsAuthenticationError,
    VaccinationsForbiddenError,
    VaccinationsInvalidResponseError,
)


def payload() -> dict[str, object]:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "clientPetId": "22222222-2222-2222-2222-222222222222",
        "recordId": "33333333-3333-3333-3333-333333333333",
        "vaccineName": "Rabia",
        "doseNumber": 1,
        "applicationDate": "2026-01-15T10:00:00Z",
        "nextDoseDate": "2027-01-15T10:00:00Z",
        "createdAt": "2026-01-15T10:05:00Z",
    }


@pytest.mark.anyio
async def test_list_owned_calls_vaccinations_route_with_jwt() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/vaccinations/mine"
        assert request.headers["Authorization"] == "Bearer token"
        return httpx.Response(200, json=[payload()])

    gateway = DotNetVaccinationsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    record = (await gateway.list_owned("token"))[0]
    assert record.vaccine_name == "Rabia"
    assert record.application_date.tzinfo is UTC


@pytest.mark.anyio
async def test_list_owned_raises_forbidden_on_403() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403)

    gateway = DotNetVaccinationsGateway(
        "https://backend.test", 2, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )
    with pytest.raises(VaccinationsForbiddenError):
        await gateway.list_owned("token")
