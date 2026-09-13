from collections.abc import Mapping
from datetime import UTC, date, datetime
from typing import Any
from uuid import UUID

import httpx

from app.ports.appointments_gateway import (
    AppointmentBookingOptions,
    AppointmentBookingPet,
    AppointmentBookingRequest,
    AppointmentBookingService,
    AppointmentBookingSlot,
    AppointmentBookingVeterinarian,
    AppointmentItem,
    AppointmentNotFoundError,
    AppointmentRescheduleRequest,
    AppointmentsAuthenticationError,
    AppointmentsConflictError,
    AppointmentScope,
    AppointmentsForbiddenError,
    AppointmentsInvalidResponseError,
    AppointmentsRequestError,
    AppointmentsUnavailableError,
    BookingCatalogItem,
    InlinePetRegistration,
    OwnerContactRequest,
    OwnerContactResult,
    OwnerNotFoundError,
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
            "/api/bot/appointments", bearer_token, params={"scope": scope.value}
        )
        payload = self._json(response)
        if not isinstance(payload, list):
            raise AppointmentsInvalidResponseError("Backend returned an invalid appointments list")
        return tuple(self._appointment(item) for item in payload)

    async def get_owned(self, appointment_id: UUID, bearer_token: str) -> AppointmentItem:
        response = await self._request(f"/api/bot/appointments/{appointment_id}", bearer_token)
        return self._appointment(self._json(response))

    async def get_booking_options(self, bearer_token: str) -> AppointmentBookingOptions:
        response = await self._request("/api/bot/appointments/booking/options", bearer_token)
        payload = self._json(response)
        if not isinstance(payload, Mapping):
            raise AppointmentsInvalidResponseError("Backend returned invalid booking options")
        try:
            pets = tuple(
                AppointmentBookingPet(id=UUID(str(item["id"])), name=self._text(item, "name"))
                for item in self._items(payload, "pets")
            )
            services = tuple(
                AppointmentBookingService(
                    id=UUID(str(item["id"])),
                    name=self._text(item, "name"),
                    duration_minutes=self._positive_int(item, "durationMinutes"),
                )
                for item in self._items(payload, "services")
            )
            veterinarians = tuple(
                AppointmentBookingVeterinarian(
                    id=UUID(str(item["id"])),
                    full_name=self._text(item, "fullName"),
                    specialty_name=self._text(item, "specialtyName"),
                )
                for item in self._items(payload, "veterinarians")
            )
            requires_phone = payload["requiresRequesterPhoneNumber"]
            if not isinstance(requires_phone, bool):
                raise ValueError("requiresRequesterPhoneNumber")
        except (KeyError, TypeError, ValueError) as exc:
            raise AppointmentsInvalidResponseError(
                "Backend returned invalid booking options"
            ) from exc
        return AppointmentBookingOptions(pets, services, veterinarians, requires_phone)

    async def list_booking_slots(
        self,
        veterinarian_id: UUID,
        service_id: UUID,
        booking_date: date,
        bearer_token: str,
    ) -> tuple[AppointmentBookingSlot, ...]:
        response = await self._request(
            "/api/bot/appointments/booking/slots",
            bearer_token,
            params={
                "veterinarianId": str(veterinarian_id),
                "serviceId": str(service_id),
                "date": booking_date.isoformat(),
            },
        )
        payload = self._json(response)
        if not isinstance(payload, list) or any(not isinstance(item, Mapping) for item in payload):
            raise AppointmentsInvalidResponseError("Backend returned invalid booking slots")
        try:
            return tuple(
                AppointmentBookingSlot(
                    availability_id=UUID(str(item["availabilityId"])),
                    scheduled_start_utc=self._datetime(item["scheduledStartUtc"]),
                    scheduled_end_utc=self._datetime(item["scheduledEndUtc"]),
                )
                for item in payload
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AppointmentsInvalidResponseError(
                "Backend returned invalid booking slots"
            ) from exc

    async def create_owned(
        self,
        booking: AppointmentBookingRequest,
        idempotency_key: str,
        bearer_token: str,
    ) -> AppointmentItem:
        response = await self._request(
            "/api/bot/appointments",
            bearer_token,
            method="POST",
            json_body={
                "petId": str(booking.pet_id),
                "veterinarianId": str(booking.veterinarian_id),
                "serviceId": str(booking.service_id),
                "scheduledStartUtc": self._utc_iso(booking.scheduled_start_utc),
                "notes": booking.notes,
                "requesterPhoneNumber": booking.requester_phone_number,
            },
            extra_headers={"Idempotency-Key": idempotency_key},
        )
        return self._appointment(self._json(response))

    async def cancel_owned(
        self, appointment_id: UUID, bearer_token: str, *, comment: str | None = None
    ) -> None:
        await self._request(
            f"/api/bot/appointments/{appointment_id}/cancel",
            bearer_token,
            method="PATCH",
            json_body={"comment": comment},
        )

    async def reschedule_owned(
        self,
        appointment_id: UUID,
        request: AppointmentRescheduleRequest,
        bearer_token: str,
    ) -> None:
        await self._request(
            f"/api/bot/appointments/{appointment_id}/reschedule",
            bearer_token,
            method="PATCH",
            json_body={
                "availabilityId": str(request.availability_id),
                "scheduledStart": self._utc_iso(request.scheduled_start_utc),
                "scheduledEnd": self._utc_iso(request.scheduled_end_utc),
                "requesterPhoneNumber": request.requester_phone_number,
                "notes": request.notes,
            },
        )

    async def request_reschedule_code(
        self,
        appointment_id: UUID,
        phone: str,
        availability_id: UUID,
        scheduled_start_utc: datetime,
        scheduled_end_utc: datetime,
        bearer_token: str,
    ) -> UUID:
        response = await self._request(
            f"/api/appointments/mine/{appointment_id}/request-code",
            bearer_token,
            method="POST",
            json_body={
                "phoneNumber": phone,
                "action": "Reschedule",
                "reschedule": {
                    "availabilityId": str(availability_id),
                    "scheduledStart": self._utc_iso(scheduled_start_utc),
                    "scheduledEnd": self._utc_iso(scheduled_end_utc),
                    "notes": None,
                },
            },
        )
        payload = self._json(response)
        if not isinstance(payload, dict) or "sessionId" not in payload:
            raise AppointmentsInvalidResponseError("Backend returned invalid session response")
        try:
            return UUID(str(payload["sessionId"]))
        except (TypeError, ValueError) as exc:
            raise AppointmentsInvalidResponseError("Backend returned invalid session ID") from exc

    async def confirm_reschedule_code(
        self,
        appointment_id: UUID,
        phone: str,
        code: str,
        bearer_token: str,
    ) -> None:
        await self._request(
            f"/api/appointments/mine/{appointment_id}/confirm-code",
            bearer_token,
            method="POST",
            json_body={
                "phoneNumber": phone,
                "code": code,
                "action": "Reschedule",
            },
        )

    async def find_or_create_owner(
        self, contact: OwnerContactRequest, bearer_token: str
    ) -> OwnerContactResult:
        response = await self._request(
            "/api/bot/clients/find-or-create",
            bearer_token,
            method="POST",
            json_body={
                "identificationNumber": contact.identification_number,
                "fullName": contact.full_name,
                "email": contact.email,
                "phoneNumber": contact.phone_number,
            },
        )
        payload = self._json(response)
        if not isinstance(payload, Mapping):
            raise AppointmentsInvalidResponseError("Backend returned invalid owner response")
        try:
            created = payload["created"]
            if not isinstance(created, bool):
                raise ValueError("created")
            access_token = self._text(payload, "accessToken")
            user_id = payload.get("userId")
            user_account_id = payload.get("userAccountId")
            return OwnerContactResult(
                client_id=UUID(str(payload["clientId"])),
                identification_number=self._text(payload, "identificationNumber"),
                created=created,
                access_token=access_token,
                user_id=UUID(str(user_id)) if user_id is not None else None,
                user_account_id=UUID(str(user_account_id)) if user_account_id is not None else None,
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AppointmentsInvalidResponseError(
                "Backend returned invalid owner response"
            ) from exc

    async def get_booking_options_by_identification(
        self, identification_number: str, bearer_token: str
    ) -> AppointmentBookingOptions:
        response = await self._request(
            f"/api/bot/appointments/booking/options/by-identification/{identification_number}",
            bearer_token,
        )
        payload = self._json(response)
        if not isinstance(payload, Mapping):
            raise AppointmentsInvalidResponseError("Backend returned invalid booking options")
        try:
            pets = tuple(
                AppointmentBookingPet(id=UUID(str(item["id"])), name=self._text(item, "name"))
                for item in self._items(payload, "pets")
            )
            services = tuple(
                AppointmentBookingService(
                    id=UUID(str(item["id"])),
                    name=self._text(item, "name"),
                    duration_minutes=self._positive_int(item, "durationMinutes"),
                )
                for item in self._items(payload, "services")
            )
            veterinarians = tuple(
                AppointmentBookingVeterinarian(
                    id=UUID(str(item["id"])),
                    full_name=self._text(item, "fullName"),
                    specialty_name=self._text(item, "specialtyName"),
                )
                for item in self._items(payload, "veterinarians")
            )
            requires_phone = payload["requiresRequesterPhoneNumber"]
            if not isinstance(requires_phone, bool):
                raise ValueError("requiresRequesterPhoneNumber")
        except (KeyError, TypeError, ValueError) as exc:
            raise AppointmentsInvalidResponseError(
                "Backend returned invalid booking options"
            ) from exc
        return AppointmentBookingOptions(pets, services, veterinarians, requires_phone)

    async def list_by_identification(
        self, identification_number: str, scope: AppointmentScope, bearer_token: str
    ) -> tuple[AppointmentItem, ...]:
        response = await self._request(
            f"/api/bot/appointments/by-identification/{identification_number}",
            bearer_token,
            params={"scope": scope.value},
        )
        payload = self._json(response)
        if not isinstance(payload, list):
            raise AppointmentsInvalidResponseError("Backend returned an invalid appointments list")
        return tuple(self._appointment(item) for item in payload)

    async def get_by_identification(
        self, appointment_id: UUID, identification_number: str, bearer_token: str
    ) -> AppointmentItem:
        # Backend has no single-appointment-by-identification route; resolve via list.
        items = await self.list_by_identification(
            identification_number, AppointmentScope.ALL, bearer_token
        )
        for item in items:
            if item.id == appointment_id:
                return item
        raise AppointmentNotFoundError("Appointment was not found")

    async def create_by_identification(
        self,
        identification_number: str,
        booking: AppointmentBookingRequest,
        idempotency_key: str,
        bearer_token: str,
    ) -> AppointmentItem:
        response = await self._request(
            "/api/bot/appointments/by-identification",
            bearer_token,
            method="POST",
            json_body={
                "identificationNumber": identification_number,
                "petId": str(booking.pet_id),
                "veterinarianId": str(booking.veterinarian_id),
                "serviceId": str(booking.service_id),
                "scheduledStartUtc": self._utc_iso(booking.scheduled_start_utc),
                "notes": booking.notes,
                "requesterPhoneNumber": booking.requester_phone_number,
            },
            extra_headers={"Idempotency-Key": idempotency_key},
        )
        return self._appointment(self._json(response))

    async def cancel_by_identification(
        self,
        appointment_id: UUID,
        identification_number: str,
        bearer_token: str,
        *,
        comment: str | None = None,
    ) -> None:
        await self._request(
            f"/api/bot/appointments/{appointment_id}/cancel-by-identification",
            bearer_token,
            method="PATCH",
            json_body={
                "identificationNumber": identification_number,
                "comment": comment,
            },
        )

    async def reschedule_by_identification(
        self,
        appointment_id: UUID,
        identification_number: str,
        request: AppointmentRescheduleRequest,
        bearer_token: str,
    ) -> None:
        await self._request(
            f"/api/bot/appointments/{appointment_id}/reschedule-by-identification",
            bearer_token,
            method="PATCH",
            json_body={
                "identificationNumber": identification_number,
                "availabilityId": str(request.availability_id),
                "scheduledStart": self._utc_iso(request.scheduled_start_utc),
                "scheduledEnd": self._utc_iso(request.scheduled_end_utc),
                "requesterPhoneNumber": request.requester_phone_number,
                "notes": request.notes,
            },
        )

    async def create_pet_by_identification(
        self,
        identification_number: str,
        registration: InlinePetRegistration,
        bearer_token: str,
    ) -> AppointmentBookingPet:
        # No pets-by-cedula API: use delegated telegram_agent token on POST /api/bot/pets.
        del identification_number
        response = await self._request(
            "/api/bot/pets",
            bearer_token,
            method="POST",
            json_body={
                "name": registration.name,
                "age": registration.age,
                "gender": registration.gender,
                "weight": registration.weight,
                "observations": registration.observations,
                "speciesId": str(registration.species_id),
                "raceId": str(registration.race_id),
            },
        )
        payload = self._json(response)
        if not isinstance(payload, Mapping):
            raise AppointmentsInvalidResponseError("Backend returned invalid pet response")
        try:
            return AppointmentBookingPet(
                id=UUID(str(payload["id"])),
                name=self._text(payload, "name"),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AppointmentsInvalidResponseError(
                "Backend returned invalid pet response"
            ) from exc

    async def list_pet_species(self, bearer_token: str) -> tuple[BookingCatalogItem, ...]:
        return await self._catalog("/api/species", bearer_token)

    async def list_pet_races(
        self, species_id: UUID, bearer_token: str
    ) -> tuple[BookingCatalogItem, ...]:
        return await self._catalog(f"/api/races?speciesId={species_id}", bearer_token)

    async def _catalog(self, path: str, bearer_token: str) -> tuple[BookingCatalogItem, ...]:
        payload = self._json(await self._request(path, bearer_token))
        if not isinstance(payload, list):
            raise AppointmentsInvalidResponseError("Backend returned an invalid catalog")
        try:
            return tuple(
                BookingCatalogItem(id=UUID(str(item["id"])), name=str(item["name"]))
                for item in payload
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise AppointmentsInvalidResponseError(
                "Backend returned an invalid catalog"
            ) from exc

    async def _request(
        self,
        path: str,
        bearer_token: str,
        *,
        method: str = "GET",
        params: dict[str, str] | None = None,
        json_body: dict[str, object] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        headers = {"Authorization": f"Bearer {bearer_token}", **(extra_headers or {})}
        try:
            response = await self._client.request(
                method, path, params=params, json=json_body, headers=headers
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
            # Distinguishes missing owner for identification-scoped ops when backend
            # returns a typed problem; fall back to appointment-not-found otherwise.
            detail = ""
            try:
                body = response.json()
                if isinstance(body, Mapping):
                    detail = str(body.get("title") or body.get("detail") or "").casefold()
            except ValueError:
                detail = ""
            if "cedula" in detail or "cédula" in detail or "identification" in detail or "owner" in detail:
                raise OwnerNotFoundError("Owner was not found for identification")
            raise AppointmentNotFoundError("Appointment was not found")
        if response.status_code == 409:
            raise AppointmentsConflictError("Appointment booking conflicts with current state")
        if response.status_code in {400, 422}:
            raise AppointmentsRequestError("Backend rejected appointment booking data")
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

    @staticmethod
    def _utc_iso(value: datetime) -> str:
        if value.tzinfo is None:
            raise AppointmentsInvalidResponseError("Appointment start must include a timezone")
        return value.astimezone(UTC).isoformat().replace("+00:00", "Z")

    @staticmethod
    def _items(payload: Mapping[str, object], key: str) -> tuple[Mapping[str, object], ...]:
        values = payload[key]
        if not isinstance(values, list) or any(not isinstance(item, Mapping) for item in values):
            raise ValueError(key)
        return tuple(values)

    @staticmethod
    def _text(value: Mapping[str, object], key: str) -> str:
        text = value[key]
        if not isinstance(text, str) or not text.strip():
            raise ValueError(key)
        return text.strip()

    @staticmethod
    def _positive_int(value: Mapping[str, object], key: str) -> int:
        number = value[key]
        if not isinstance(number, int) or isinstance(number, bool) or number <= 0:
            raise ValueError(key)
        return number

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
