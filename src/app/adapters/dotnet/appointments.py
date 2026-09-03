from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any
from uuid import UUID

import httpx

from app.ports.appointments_gateway import (
    AppointmentItem,
    AppointmentNotFoundError,
    AppointmentsAuthenticationError,
    AppointmentScope,
    AppointmentsForbiddenError,
    AppointmentsInvalidResponseError,
    AppointmentsUnavailableError,
)


class DotNetAppointmentsGateway:
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

    async def list_owned(
        self, scope: AppointmentScope, bearer_token: str
    ) -> tuple[AppointmentItem, ...]:
        response = await self._request(
            "/api/appointments/mine", bearer_token, params={"scope": scope.value}
        )
        payload = self._json(response)
        if not isinstance(payload, list):
            raise AppointmentsInvalidResponseError("Backend returned an invalid appointments list")
        return tuple(self._appointment(item) for item in payload)

    async def get_owned(self, appointment_id: UUID, bearer_token: str) -> AppointmentItem:
        response = await self._request(f"/api/appointments/mine/{appointment_id}", bearer_token)
        return self._appointment(self._json(response))

    async def _request(
        self, path: str, bearer_token: str, *, params: dict[str, str] | None = None
    ) -> httpx.Response:
        try:
            response = await self._client.get(
                path, params=params, headers={"Authorization": f"Bearer {bearer_token}"}
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise AppointmentsUnavailableError("Veterinary appointments are unavailable") from exc
        if len(response.content) > self._max_response_bytes:
            raise AppointmentsInvalidResponseError("Backend response exceeds the safe limit")
        if response.status_code == 401:
            raise AppointmentsAuthenticationError("Backend rejected appointment authentication")
        if response.status_code == 403:
            raise AppointmentsForbiddenError("Backend denied appointment access")
        if response.status_code == 404:
            raise AppointmentNotFoundError("Appointment was not found")
        if response.status_code >= 500:
            raise AppointmentsUnavailableError("Veterinary appointments are unavailable")
        if response.status_code >= 400:
            raise AppointmentsInvalidResponseError("Backend rejected the appointment request")
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise AppointmentsInvalidResponseError(
                "Backend returned invalid appointment JSON"
            ) from exc

    @staticmethod
    def _appointment(value: object) -> AppointmentItem:
        if not isinstance(value, Mapping):
            raise AppointmentsInvalidResponseError("Backend returned an invalid appointment")
        try:

            def required_text(key: str) -> str:
                text = value[key]
                if not isinstance(text, str) or not text.strip():
                    raise ValueError(key)
                return text.strip()

            notes = value.get("notes")
            if notes is not None and not isinstance(notes, str):
                raise ValueError("notes")
            return AppointmentItem(
                id=UUID(str(value["id"])),
                client_pet_id=UUID(str(value["clientPetId"])),
                pet_name=required_text("petName"),
                veterinarian_id=UUID(str(value["veterinarianId"])),
                veterinarian_name=required_text("veterinarianName"),
                service_id=UUID(str(value["serviceId"])),
                service_name=required_text("serviceName"),
                status_id=UUID(str(value["statusId"])),
                status_name=required_text("statusName"),
                availability_id=UUID(str(value["availabilityId"])),
                scheduled_start=DotNetAppointmentsGateway._datetime(value["scheduledStart"]),
                scheduled_end=DotNetAppointmentsGateway._datetime(value["scheduledEnd"]),
                notes=notes.strip() if notes else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AppointmentsInvalidResponseError(
                "Backend returned an invalid appointment"
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
