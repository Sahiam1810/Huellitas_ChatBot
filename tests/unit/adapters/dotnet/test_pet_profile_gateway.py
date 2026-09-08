from datetime import UTC, datetime
from uuid import UUID

import httpx
import pytest

import app.ports.pet_profile_gateway as pet_profile_ports
from app.adapters.dotnet.pet_profile import DotNetPetProfileGateway
from app.ports.pet_profile_gateway import (
    PetProfileAuthenticationError,
    PetProfilePatch,
    PetProfileUnavailableError,
    PetProfileVersionConflictError,
    PetRegistration,
)


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


@pytest.mark.anyio
async def test_list_owned_maps_missing_client_profile_separately() -> None:
    error_type = getattr(
        pet_profile_ports,
        "PetProfileOwnerProfileNotFoundError",
        None,
    )
    assert error_type is not None

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/pets/mine"
        return httpx.Response(
            404,
            json={"detail": "El usuario autenticado no tiene un perfil de cliente asociado."},
        )

    gateway = DotNetPetProfileGateway(
        "http://backend.test",
        5,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(error_type) as captured:
        await gateway.list_owned("jwt-secret")

    assert "jwt-secret" not in str(captured.value)
    await gateway.close()


@pytest.mark.anyio
async def test_create_owned_posts_registration_and_returns_authoritative_profile() -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST"
        assert request.url.path == "/api/pets/mine"
        assert request.headers["authorization"] == "Bearer jwt-secret"
        assert request.content.decode() == (
            '{"name":"Luna","age":4,"gender":"F","weight":12.5,'
            '"observations":null,"speciesId":"22222222-2222-2222-2222-222222222222",'
            '"raceId":"33333333-3333-3333-3333-333333333333"}'
        )
        return httpx.Response(201, json=profile_payload())

    gateway = DotNetPetProfileGateway(
        "http://backend.test",
        5,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    registration = PetRegistration(
        name="Luna",
        age=4,
        gender="F",
        weight=12.5,
        observations=None,
        species_id=UUID("22222222-2222-2222-2222-222222222222"),
        race_id=UUID("33333333-3333-3333-3333-333333333333"),
    )

    created = await gateway.create_owned("jwt-secret", registration)

    assert created.name == "Luna"
    assert created.race_name == "Mestizo"
    await gateway.close()


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("status", "error_type"),
    [(401, PetProfileAuthenticationError), (503, PetProfileUnavailableError)],
)
async def test_create_owned_maps_backend_errors_without_leaking_payload(
    status: int, error_type: type[Exception]
) -> None:
    async def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, json={"detail": "rejected"})

    gateway = DotNetPetProfileGateway(
        "http://backend.test",
        5,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )
    registration = PetRegistration(
        "Luna",
        4,
        "F",
        12.5,
        None,
        UUID("22222222-2222-2222-2222-222222222222"),
        UUID("33333333-3333-3333-3333-333333333333"),
    )

    with pytest.raises(error_type) as captured:
        await gateway.create_owned("jwt-secret", registration)

    assert "jwt-secret" not in str(captured.value)
    assert "Luna" not in str(captured.value)
    await gateway.close()


@pytest.mark.anyio
async def test_list_races_filters_the_catalog_by_species_id() -> None:
    species_id = UUID("22222222-2222-2222-2222-222222222222")

    async def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/races"
        assert request.url.params.get("speciesId") == str(species_id)
        assert request.headers["authorization"] == "Bearer jwt-secret"
        return httpx.Response(
            200,
            json=[
                {
                    "id": "33333333-3333-3333-3333-333333333333",
                    "name": "Mestizo",
                    "speciesId": str(species_id),
                }
            ],
        )

    gateway = DotNetPetProfileGateway(
        "http://backend.test",
        5,
        client=httpx.AsyncClient(transport=httpx.MockTransport(handler)),
    )

    races = await gateway.list_races(species_id, "jwt-secret")

    assert [race.name for race in races] == ["Mestizo"]
    await gateway.close()
