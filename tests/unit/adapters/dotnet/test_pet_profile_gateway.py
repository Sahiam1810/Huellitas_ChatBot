from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

from app.adapters.dotnet.pet_profile import DotNetPetProfileGateway
from app.ports.pet_profile_gateway import PetProfilePatch, PetProfileVersionConflictError


def profile_payload() -> dict[str, object]:
    return {
        "id": "11111111-1111-1111-1111-111111111111",
        "name": "Luna",
        "age": 4,
        "gender": "F",
        "weight": 12.5,
        "observations": "Sana",
        "speciesId": "22222222-2222-2222-2222-222222222222",
        "speciesName": "Canino",
        "raceId": "33333333-3333-3333-3333-333333333333",
        "raceName": "Mestizo",
        "updatedAt": "2026-09-02T15:00:00Z",
    }


@pytest.mark.anyio
async def test_list_owned_deserializes_profile_and_forwards_bearer_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/pets/mine"
        assert request.headers["authorization"] == "Bearer jwt-secret"
        return httpx.Response(200, json=[profile_payload()])

    client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    gateway = DotNetPetProfileGateway("http://backend.test", 5, client=client)

    profiles = await gateway.list_owned("jwt-secret")

    profile = profiles[0]
    assert profile.name == "Luna"
    assert profile.species_name == "Canino"
    assert profile.updated_at == datetime(2026, 9, 2, 15, tzinfo=UTC)
    await gateway.close()


@pytest.mark.anyio
async def test_update_owned_maps_conflict_without_leaking_token() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "PATCH"
        return httpx.Response(409, json={"detail": "stale"})

    gateway = DotNetPetProfileGateway(
        "http://backend.test",
        5,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    patch = PetProfilePatch(
        expected_updated_at=datetime(2026, 9, 2, 15, tzinfo=UTC),
        name="Nala",
    )

    with pytest.raises(PetProfileVersionConflictError) as captured:
        await gateway.update_owned(
            "jwt-secret",
            UUID("11111111-1111-1111-1111-111111111111"),
            patch,
        )

    assert "jwt-secret" not in str(captured.value)
    await gateway.close()
