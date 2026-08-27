from dataclasses import dataclass
from typing import Protocol, runtime_checkable
from uuid import UUID


@dataclass(frozen=True, slots=True)
class AuthenticatedPrincipal:
    account_id: UUID
    person_id: UUID
    role_id: UUID
    role: str
    username: str
    email: str
    token_id: UUID


@runtime_checkable
class TokenValidator(Protocol):
    def validate(self, token: str) -> AuthenticatedPrincipal: ...
