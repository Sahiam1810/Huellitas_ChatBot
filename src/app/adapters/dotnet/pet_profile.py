from collections.abc import Mapping
from datetime import datetime
from typing import Any
from uuid import UUID

import httpx

from app.ports.pet_profile_gateway import (
    CatalogItem,
    PetProfile,
    PetProfileAuthenticationError,
    PetProfileForbiddenError,
    PetProfileInvalidResponseError,
    PetProfileNotFoundError,
    PetProfileOwnerProfileNotFoundError,
    PetProfilePatch,
    PetProfileUnavailableError,
    PetProfileVersionConflictError,
    PetRegistration,
)


class DotNetPetProfileGateway:
    def __init__(
        self,
        base_url: str,
        timeout_seconds: float,
        *,
        max_response_bytes: int = 1_048_576,
        client: httpx.AsyncClient | None = None,
    ) -> None:
        self._owns_client = client is None
        self._client = client or httpx.AsyncClient(
            base_url=base_url.rstrip("/"), timeout=timeout_seconds
        )
        if client is not None:
            self._client.base_url = httpx.URL(base_url.rstrip("/"))
        self._max_response_bytes = max_response_bytes

    async def list_owned(self, bearer_token: str) -> tuple[PetProfile, ...]:
        try:
            response = await self._request("GET", "/api/pets/mine", bearer_token)
        except PetProfileNotFoundError:
            raise PetProfileOwnerProfileNotFoundError(
                "Authenticated owner profile was not found"
            ) from None
        payload = self._json(response)
        if not isinstance(payload, list):
            raise PetProfileInvalidResponseError("Backend returned an invalid pet list")
        return tuple(self._profile(item) for item in payload)

    async def update_owned(
        self, bearer_token: str, pet_id: UUID, patch: PetProfilePatch
    ) -> PetProfile:
        body: dict[str, object] = {
            "expectedUpdatedAt": patch.expected_updated_at.isoformat(),
            "changeObservations": patch.change_observations,
        }
        for key, value in (
            ("name", patch.name),
            ("age", patch.age),
            ("gender", patch.gender),
            ("weight", patch.weight),
            ("speciesId", patch.species_id),
            ("raceId", patch.race_id),
        ):
            if value is not None:
                body[key] = str(value) if isinstance(value, UUID) else value
        if patch.change_observations:
            body["observations"] = patch.observations
        response = await self._request(
            "PATCH", f"/api/pets/mine/{pet_id}", bearer_token, json=body
        )
        return self._profile(self._json(response))

    async def create_owned(
        self, bearer_token: str, registration: PetRegistration
    ) -> PetProfile:
        response = await self._request(
            "POST",
            "/api/pets/mine",
            bearer_token,
            json={
                "name": registration.name,
                "age": registration.age,
                "gender": registration.gender,
                "weight": registration.weight,
                "observations": registration.observations,
                "speciesId": str(registration.species_id),
                "raceId": str(registration.race_id),
            },
        )
        return self._profile(self._json(response))

    async def list_species(self, bearer_token: str) -> tuple[CatalogItem, ...]:
        return await self._catalog("/api/species", bearer_token)

    async def list_races(
        self, species_id: UUID, bearer_token: str
    ) -> tuple[CatalogItem, ...]:
        return await self._catalog(
            f"/api/races?speciesId={species_id}", bearer_token
        )

    async def _catalog(self, path: str, token: str) -> tuple[CatalogItem, ...]:
        payload = self._json(await self._request("GET", path, token))
        if not isinstance(payload, list):
            raise PetProfileInvalidResponseError("Backend returned an invalid catalog")
        try:
            return tuple(CatalogItem(id=UUID(item["id"]), name=item["name"]) for item in payload)
        except (KeyError, TypeError, ValueError) as exc:
            raise PetProfileInvalidResponseError("Backend returned an invalid catalog") from exc

    async def _request(
        self, method: str, path: str, token: str, **kwargs: object
    ) -> httpx.Response:
        try:
            response = await self._client.request(
                method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise PetProfileUnavailableError("Veterinary backend is unavailable") from exc
        if len(response.content) > self._max_response_bytes:
            raise PetProfileInvalidResponseError("Backend response exceeds the safe limit")
        errors = {
            401: PetProfileAuthenticationError,
            403: PetProfileForbiddenError,
            404: PetProfileNotFoundError,
            409: PetProfileVersionConflictError,
        }
        error = errors.get(response.status_code)
        if error is not None:
            raise error("Veterinary backend rejected the pet-profile operation")
        if response.status_code >= 500:
            raise PetProfileUnavailableError("Veterinary backend is unavailable")
        if response.status_code >= 400:
            raise PetProfileInvalidResponseError("Veterinary backend rejected the request")
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise PetProfileInvalidResponseError("Backend returned invalid JSON") from exc

    @staticmethod
    def _profile(value: object) -> PetProfile:
        if not isinstance(value, Mapping):
            raise PetProfileInvalidResponseError("Backend returned an invalid pet profile")
        try:
            return PetProfile(
                id=UUID(str(value["id"])),
                name=str(value["name"]),
                age=int(value["age"]),
                gender=str(value["gender"]),
                weight=float(value["weight"]),
                observations=(
                    str(value["observations"]) if value.get("observations") is not None else None
                ),
                species_id=UUID(str(value["speciesId"])),
                species_name=str(value["speciesName"]),
                race_id=UUID(str(value["raceId"])),
                race_name=str(value["raceName"]),
                updated_at=datetime.fromisoformat(str(value["updatedAt"]).replace("Z", "+00:00")),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise PetProfileInvalidResponseError("Backend returned an invalid pet profile") from exc

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
