from dataclasses import dataclass
from uuid import UUID

from app.ports.token_validator import AuthenticatedPrincipal


@dataclass(frozen=True, slots=True)
class ExecutionContext:
    bearer_token: str
    principal: AuthenticatedPrincipal
    execution_id: UUID
    correlation_id: UUID
