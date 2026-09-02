from collections.abc import Mapping
from decimal import Decimal, InvalidOperation
from typing import Any
from uuid import UUID

import httpx

from app.ports.services_catalog_gateway import (
    ServiceCatalogItem,
    ServicesCatalogAuthenticationError,
    ServicesCatalogForbiddenError,
    ServicesCatalogInvalidResponseError,
    ServicesCatalogUnavailableError,
)


class DotNetServicesCatalogGateway:
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

    async def list_available(self, bearer_token: str) -> tuple[ServiceCatalogItem, ...]:
        response = await self._request(
            "GET", "/api/services/available", bearer_token
        )
        payload = self._json(response)
        if not isinstance(payload, list):
            raise ServicesCatalogInvalidResponseError(
                "Backend returned an invalid service catalog"
            )
        return tuple(self._service(item) for item in payload)

    async def _request(
        self, method: str, path: str, bearer_token: str
    ) -> httpx.Response:
        try:
            response = await self._client.request(
                method,
                path,
                headers={"Authorization": f"Bearer {bearer_token}"},
            )
        except (httpx.TimeoutException, httpx.NetworkError) as exc:
            raise ServicesCatalogUnavailableError(
                "Veterinary service catalog is unavailable"
            ) from exc
        if len(response.content) > self._max_response_bytes:
            raise ServicesCatalogInvalidResponseError(
                "Backend response exceeds the safe limit"
            )
        if response.status_code == 401:
            raise ServicesCatalogAuthenticationError(
                "Backend rejected service catalog authentication"
            )
        if response.status_code == 403:
            raise ServicesCatalogForbiddenError(
                "Backend denied service catalog access"
            )
        if response.status_code >= 500:
            raise ServicesCatalogUnavailableError(
                "Veterinary service catalog is unavailable"
            )
        if response.status_code >= 400:
            raise ServicesCatalogInvalidResponseError(
                "Backend rejected the service catalog request"
            )
        return response

    @staticmethod
    def _json(response: httpx.Response) -> Any:
        try:
            return response.json()
        except ValueError as exc:
            raise ServicesCatalogInvalidResponseError(
                "Backend returned invalid service catalog JSON"
            ) from exc

    @staticmethod
    def _service(value: object) -> ServiceCatalogItem:
        if not isinstance(value, Mapping):
            raise ServicesCatalogInvalidResponseError(
                "Backend returned an invalid service catalog item"
            )
        try:
            type_name = value["typeServiceName"]
            name = value["name"]
            duration = value["durationMinutes"]
            if not isinstance(type_name, str) or not type_name.strip():
                raise ValueError("invalid category")
            if not isinstance(name, str) or not name.strip():
                raise ValueError("invalid name")
            if isinstance(duration, bool) or not isinstance(duration, int) or duration <= 0:
                raise ValueError("invalid duration")
            price = Decimal(str(value["price"]))
            if not price.is_finite() or price < 0:
                raise ValueError("invalid price")
            return ServiceCatalogItem(
                id=UUID(str(value["id"])),
                type_service_id=UUID(str(value["typeServiceId"])),
                type_service_name=type_name.strip(),
                name=name.strip(),
                duration_minutes=duration,
                price=price,
            )
        except (KeyError, TypeError, ValueError, InvalidOperation) as exc:
            raise ServicesCatalogInvalidResponseError(
                "Backend returned an invalid service catalog item"
            ) from exc

    async def close(self) -> None:
        if self._owns_client:
            await self._client.aclose()
