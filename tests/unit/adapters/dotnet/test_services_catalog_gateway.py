from decimal import Decimal
from uuid import UUID

import httpx
import pytest

from app.adapters.dotnet.services_catalog import DotNetServicesCatalogGateway
from app.ports.services_catalog_gateway import (
    ServicesCatalogAuthenticationError,
    ServicesCatalogForbiddenError,
    ServicesCatalogInvalidResponseError,
    ServicesCatalogUnavailableError,
)


def catalog_payload() -> list[dict[str, object]]:
    return [
        {
            "id": "11111111-1111-1111-1111-111111111111",
            "typeServiceId": "22222222-2222-2222-2222-222222222222",
            "typeServiceName": "Consulta",
            "name": "Consulta general",
            "durationMinutes": 30,
            "price": 55000.0,
            "isActive": True,
            "createdAt": "2026-09-02T12:00:00Z",
        }
    ]


@pytest.mark.anyio
async def test_list_available_parses_the_official_catalog_contract() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/api/services/available"
        assert request.headers["Authorization"].startswith("Bearer ")
        return httpx.Response(200, json=catalog_payload())

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = DotNetServicesCatalogGateway("https://backend.test", 2, client=client)

    result = await gateway.list_available("delegated-token")

    service = result[0]
    assert service.id == UUID("11111111-1111-1111-1111-111111111111")
    assert service.type_service_id == UUID("22222222-2222-2222-2222-222222222222")
    assert service.type_service_name == "Consulta"
    assert service.name == "Consulta general"
    assert service.duration_minutes == 30
    assert service.price == Decimal("55000.0")


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "expected_error"),
    [
        (401, ServicesCatalogAuthenticationError),
        (403, ServicesCatalogForbiddenError),
        (503, ServicesCatalogUnavailableError),
    ],
)
async def test_list_available_maps_backend_failures_to_safe_errors(
    status: int,
    expected_error: type[Exception],
) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(status, text="sensitive body"))
    )
    gateway = DotNetServicesCatalogGateway("https://backend.test", 2, client=client)

    with pytest.raises(expected_error, match="catalog") as captured:
        await gateway.list_available("delegated-token")

    assert "sensitive body" not in str(captured.value)


@pytest.mark.anyio
async def test_list_available_maps_timeout_to_unavailable() -> None:
    async def timeout(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("secret upstream address", request=request)

    client = httpx.AsyncClient(transport=httpx.MockTransport(timeout))
    gateway = DotNetServicesCatalogGateway("https://backend.test", 2, client=client)

    with pytest.raises(ServicesCatalogUnavailableError, match="unavailable"):
        await gateway.list_available("delegated-token")


@pytest.mark.anyio
@pytest.mark.parametrize(
    "payload",
    [
        {"not": "a list"},
        [{"id": "invalid"}],
        [
            {
                **catalog_payload()[0],
                "durationMinutes": 0,
            }
        ],
    ],
)
async def test_list_available_rejects_malformed_contract(payload: object) -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, json=payload))
    )
    gateway = DotNetServicesCatalogGateway("https://backend.test", 2, client=client)

    with pytest.raises(ServicesCatalogInvalidResponseError, match="invalid"):
        await gateway.list_available("delegated-token")


@pytest.mark.anyio
async def test_list_available_rejects_oversized_response() -> None:
    client = httpx.AsyncClient(
        transport=httpx.MockTransport(lambda _: httpx.Response(200, content=b"[]" * 20))
    )
    gateway = DotNetServicesCatalogGateway(
        "https://backend.test", 2, max_response_bytes=8, client=client
    )

    with pytest.raises(ServicesCatalogInvalidResponseError, match="safe limit"):
        await gateway.list_available("delegated-token")
