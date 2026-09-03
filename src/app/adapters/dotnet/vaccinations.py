from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from app.ports.vaccinations_gateway import (
    VaccinationRecord,
    VaccinationsAuthenticationError,
    VaccinationsForbiddenError,
    VaccinationsGatewayError,
    VaccinationsInvalidResponseError,
    VaccinationsNotFoundError,
    VaccinationsUnavailableError,
)


class DotNetVaccinationsGateway:
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

    async def list_owned(self, bearer_token: str) -> tuple[VaccinationRecord, ...]:
        response = await self._request("/api/vaccinations", bearer_token)
        payload = self._json(response)
        if not isinstance(payload, list):
            raise VaccinationsInvalidResponseError("Backend returned an invalid vaccinations list")
        return tuple(self._record(item) for item in payload)

    async def _request(self, path: str, bearer_token: str) -> httpx.Response:
        headers = {"Authorization": f"Bearer {bearer_token}"}
        try:
            response = await self._client.get(path, headers=headers)
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise VaccinationsUnavailableError("Vaccination records are unavailable") from exc
        if len(response.content) > self._max_response_bytes:
            raise VaccinationsInvalidResponseError("Backend response exceeds the safe limit")
        if response.status_code == 401:
            raise VaccinationsAuthenticationError("Backend rejected vaccination authentication")
        if response.status_code == 403:
            raise VaccinationsForbiddenError("Backend denied vaccination access")
        if response.status_code == 404:
            raise VaccinationsNotFoundError("Vaccination records were not found")
        if response.status_code >= 500:
            raise VaccinationsUnavailableError("Vaccination records are unavailable")
        if response.status_code >= 400:
            raise VaccinationsInvalidResponseError("Backend rejected the vaccination request")
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise VaccinationsInvalidResponseError(
                "Backend returned invalid vaccination JSON"
            ) from exc

    @staticmethod
    def _record(value: object) -> VaccinationRecord:
        if not isinstance(value, Mapping):
            raise VaccinationsInvalidResponseError("Backend returned an invalid vaccination")
        try:

            def required_text(key: str) -> str:
                text = value[key]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError(key)
                return text.strip()

            next_dose = value.get("nextDoseDate")
            if next_dose is not None and not isinstance(next_dose, str):
                raise ValueError("nextDoseDate")
            return VaccinationRecord(
                id=UUID(str(value["id"])),
                client_pet_id=UUID(str(value["clientPetId"])),
                record_id=UUID(str(value["recordId"])),
                vaccine_name=required_text("vaccineName"),
                dose_number=int(value["doseNumber"]),
                application_date=DotNetVaccinationsGateway._datetime(value["applicationDate"]),
                next_dose_date=(
                    DotNetVaccinationsGateway._datetime(next_dose) if next_dose else None
                ),
                created_at=DotNetVaccinationsGateway._datetime(value["createdAt"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise VaccinationsInvalidResponseError(
                "Backend returned an invalid vaccination"
            ) from exc

    @staticmethod
    def _datetime(value: object) -> datetime:
        if not isinstance(value, str):
            raise ValueError("date")
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("date timezone")
        return parsed.astimezone(UTC)

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
