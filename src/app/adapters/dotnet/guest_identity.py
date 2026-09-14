from collections.abc import Callable, Mapping
from typing import Any
from uuid import UUID

import httpx

from app.ports.guest_identity_gateway import (
    GuestClientMatch,
    GuestIdentityConflictError,
    GuestIdentityInvalidResponseError,
    GuestIdentityLinkConflictError,
    GuestIdentityUnavailableError,
    GuestOwnerRegistration,
)


class DotNetGuestIdentityGateway:
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

    async def lookup_by_identification(
        self, identification_number: str, bearer_token: str
    ) -> GuestClientMatch | None:
        response = await self._request(
            "GET",
            f"/api/Clients/by-identification/{identification_number}",
            bearer_token,
            not_found_is_none=True,
        )
        if response is None:
            return None
        payload = self._json(response)
        return self._match(payload, person_field="userId", client_field="id")

    async def register(
        self, registration: GuestOwnerRegistration, bearer_token: str
    ) -> GuestClientMatch:
        response = await self._request(
            "POST",
            "/api/owners/bot",
            bearer_token,
            json={
                "fullName": registration.full_name,
                "email": registration.email,
                "identificationNumber": registration.identification_number,
                "phoneNumber": registration.phone_number,
            },
            conflict_on_409=lambda code: GuestIdentityConflictError(code),
        )
        assert response is not None
        payload = self._json(response)
        return self._match(payload, person_field="userId", client_field="clientId")

    async def link_telegram_account(self, person_id: UUID, bearer_token: str) -> None:
        await self._request(
            "POST",
            "/api/integrations/telegram/bot-link",
            bearer_token,
            json={"personId": str(person_id)},
            conflict_on_409=lambda _code: GuestIdentityLinkConflictError(
                "This Telegram user is already linked to a different person"
            ),
        )

    async def _request(
        self,
        method: str,
        path: str,
        token: str,
        *,
        not_found_is_none: bool = False,
        conflict_on_409: Callable[[str], Exception] | None = None,
        **kwargs: object,
    ) -> httpx.Response | None:
        try:
            response = await self._client.request(
                method, path, headers={"Authorization": f"Bearer {token}"}, **kwargs
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise GuestIdentityUnavailableError("Veterinary backend is unavailable") from exc
        if len(response.content) > self._max_response_bytes:
            raise GuestIdentityInvalidResponseError("Backend response exceeds the safe limit")
        if response.status_code == 404 and not_found_is_none:
            return None
        if response.status_code == 409:
            if conflict_on_409 is not None:
                raise conflict_on_409(self._error_code(response))
            raise GuestIdentityInvalidResponseError("Veterinary backend rejected the request")
        if response.status_code in (401, 403):
            raise GuestIdentityUnavailableError(
                "Veterinary backend rejected the guest identification request"
            )
        if response.status_code >= 500:
            raise GuestIdentityUnavailableError("Veterinary backend is unavailable")
        if response.status_code >= 400:
            raise GuestIdentityInvalidResponseError("Veterinary backend rejected the request")
        return response

    @staticmethod
    def _error_code(response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            return ""
        if isinstance(payload, Mapping):
            code = payload.get("code")
            if isinstance(code, str):
                return code
        return ""

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise GuestIdentityInvalidResponseError("Backend returned invalid JSON") from exc

    @staticmethod
    def _match(value: object, *, person_field: str, client_field: str) -> GuestClientMatch:
        if not isinstance(value, Mapping):
            raise GuestIdentityInvalidResponseError("Backend returned an invalid client match")
        try:
            return GuestClientMatch(
                person_id=UUID(str(value[person_field])),
                client_id=UUID(str(value[client_field])),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise GuestIdentityInvalidResponseError(
                "Backend returned an invalid client match"
            ) from exc

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
