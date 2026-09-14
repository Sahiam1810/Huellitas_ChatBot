from uuid import UUID

import httpx
import pytest

from app.adapters.dotnet.guest_identity import DotNetGuestIdentityGateway
from app.ports.guest_identity_gateway import (
    GuestIdentityConflictError,
    GuestIdentityLinkConflictError,
    GuestIdentityUnavailableError,
    GuestOwnerRegistration,
)

PERSON_ID = UUID("11111111-1111-1111-1111-111111111111")
CLIENT_ID = UUID("22222222-2222-2222-2222-222222222222")


@pytest.mark.anyio
async def test_lookup_by_identification_returns_match_and_forwards_bearer_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/Clients/by-identification/123456789"
        assert request.headers["authorization"] == "Bearer guest-token"
        return httpx.Response(
            200,
            json={
                "id": str(CLIENT_ID),
                "userId": str(PERSON_ID),
                "identificationNumber": "123456789",
                "registrationDate": "2026-09-14T00:00:00Z",
            },
        )

    gateway = DotNetGuestIdentityGateway(
        "http://backend.test", 5, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    match = await gateway.lookup_by_identification("123456789", "guest-token")

    assert match is not None
    assert match.person_id == PERSON_ID
    assert match.client_id == CLIENT_ID
    await gateway.close()


@pytest.mark.anyio
async def test_lookup_by_identification_returns_none_on_404() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    gateway = DotNetGuestIdentityGateway(
        "http://backend.test", 5, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    match = await gateway.lookup_by_identification("000000000", "guest-token")

    assert match is None
    await gateway.close()


@pytest.mark.anyio
async def test_register_posts_expected_body_and_parses_response() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/owners/bot"
        assert request.method == "POST"
        body = request.content.decode()
        assert '"fullName":"Ana Perez"' in body
        assert '"identificationNumber":"123456789"' in body
        return httpx.Response(
            201, json={"userId": str(PERSON_ID), "clientId": str(CLIENT_ID)}
        )

    gateway = DotNetGuestIdentityGateway(
        "http://backend.test", 5, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    match = await gateway.register(
        GuestOwnerRegistration(
            full_name="Ana Perez",
            email="ana@example.test",
            identification_number="123456789",
            phone_number="3001234567",
        ),
        "guest-token",
    )

    assert match.person_id == PERSON_ID
    assert match.client_id == CLIENT_ID
    await gateway.close()


@pytest.mark.anyio
async def test_register_conflict_carries_the_backend_code_without_leaking_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            409,
            json={
                "type": "https://httpstatuses.com/409",
                "title": "Conflict",
                "status": 409,
                "code": "Authentication.IdentificationNumberAlreadyExists",
            },
        )

    gateway = DotNetGuestIdentityGateway(
        "http://backend.test", 5, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(GuestIdentityConflictError) as captured:
        await gateway.register(
            GuestOwnerRegistration(
                full_name="Ana Perez",
                email="ana@example.test",
                identification_number="123456789",
                phone_number="3001234567",
            ),
            "secret-token",
        )

    assert captured.value.code == "Authentication.IdentificationNumberAlreadyExists"
    assert "secret-token" not in str(captured.value)
    await gateway.close()


@pytest.mark.anyio
async def test_link_telegram_account_posts_person_id() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/integrations/telegram/bot-link"
        assert request.content.decode() == f'{{"personId":"{PERSON_ID}"}}'
        return httpx.Response(200, json={"linkId": "33333333-3333-3333-3333-333333333333"})

    gateway = DotNetGuestIdentityGateway(
        "http://backend.test", 5, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    await gateway.link_telegram_account(PERSON_ID, "guest-token")
    await gateway.close()


@pytest.mark.anyio
async def test_link_telegram_account_conflict_maps_to_link_conflict_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"code": "telegram_identity_conflict"})

    gateway = DotNetGuestIdentityGateway(
        "http://backend.test", 5, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(GuestIdentityLinkConflictError):
        await gateway.link_telegram_account(PERSON_ID, "guest-token")
    await gateway.close()


@pytest.mark.anyio
async def test_network_failure_maps_to_unavailable_error() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("boom", request=request)

    gateway = DotNetGuestIdentityGateway(
        "http://backend.test", 5, client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
    )

    with pytest.raises(GuestIdentityUnavailableError):
        await gateway.lookup_by_identification("123456789", "guest-token")
    await gateway.close()
