from dataclasses import dataclass
from decimal import Decimal
from typing import Protocol, runtime_checkable
from uuid import UUID


class ServicesCatalogGatewayError(RuntimeError):
    """Safe base error for backend service-catalog operations."""


class ServicesCatalogAuthenticationError(ServicesCatalogGatewayError):
    pass


class ServicesCatalogForbiddenError(ServicesCatalogGatewayError):
    pass


class ServicesCatalogUnavailableError(ServicesCatalogGatewayError):
    pass


class ServicesCatalogInvalidResponseError(ServicesCatalogGatewayError):
    pass


@dataclass(frozen=True, slots=True)
class ServiceCatalogItem:
    id: UUID
    type_service_id: UUID
    type_service_name: str
    name: str
    duration_minutes: int
    price: Decimal


@runtime_checkable
class ServicesCatalogGateway(Protocol):
    async def list_available(
        self, bearer_token: str
    ) -> tuple[ServiceCatalogItem, ...]: ...

    async def close(self) -> None: ...
