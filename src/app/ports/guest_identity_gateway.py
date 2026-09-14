from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


class GuestIdentityGatewayError(RuntimeError):
    """Safe base error for backend guest-identity operations."""


class GuestIdentityUnavailableError(GuestIdentityGatewayError):
    pass


class GuestIdentityInvalidResponseError(GuestIdentityGatewayError):
    pass


class GuestIdentityConflictError(GuestIdentityGatewayError):
    """Raised when registration conflicts with an existing identification, email, or phone."""

    def __init__(self, code: str) -> None:
        super().__init__(f"Backend rejected the registration: {code}")
        self.code = code


class GuestIdentityLinkConflictError(GuestIdentityGatewayError):
    """Raised when this Telegram user is already linked to a different person."""


@dataclass(frozen=True, slots=True)
class GuestClientMatch:
    person_id: UUID
    client_id: UUID


@dataclass(frozen=True, slots=True)
class GuestOwnerRegistration:
    full_name: str
    email: str
    identification_number: str
    phone_number: str


@runtime_checkable
class GuestIdentityGateway(Protocol):
    async def lookup_by_identification(
        self, identification_number: str, bearer_token: str
    ) -> GuestClientMatch | None: ...

    async def register(
        self, registration: GuestOwnerRegistration, bearer_token: str
    ) -> GuestClientMatch: ...

    async def link_telegram_account(self, person_id: UUID, bearer_token: str) -> None: ...

    async def close(self) -> None: ...
