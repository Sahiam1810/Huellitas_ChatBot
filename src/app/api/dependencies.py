from typing import Annotated

from fastapi import Request, Security
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.api.schemas.requests import MessageRequest
from app.knowledge.management_service import KnowledgeManagementService
from app.orchestration.message_handler import MessageHandler
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.exceptions import (
    AuthenticationRequiredError,
    IdentityMismatchError,
    InsufficientPermissionsError,
    KnowledgeNotConfiguredError,
    ServiceNotReadyError,
)

bearer_scheme = HTTPBearer(
    auto_error=False,
    scheme_name="AccessToken",
    description="RS256 access token issued by the Veterinaria .NET backend.",
)


def get_authenticated_principal(
    request: Request,
    credentials: Annotated[
        HTTPAuthorizationCredentials | None,
        Security(bearer_scheme),
    ],
) -> AuthenticatedPrincipal:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise AuthenticationRequiredError
    return request.app.state.dependencies.token_validator.validate(credentials.credentials)


def require_knowledge_administrator(
    request: Request,
    principal: Annotated[
        AuthenticatedPrincipal,
        Security(get_authenticated_principal),
    ],
) -> AuthenticatedPrincipal:
    if principal.role != request.app.state.settings.knowledge_admin_role.strip():
        raise InsufficientPermissionsError
    return principal


def bind_message_identity(
    payload: MessageRequest,
    principal: AuthenticatedPrincipal,
) -> tuple[str, ...]:
    if payload.user_id != principal.person_id or tuple(payload.roles) != (principal.role,):
        raise IdentityMismatchError
    return (principal.role,)


def get_message_processor(request: Request) -> MessageHandler:
    processor = request.app.state.dependencies.message_processor
    if processor is None:
        raise ServiceNotReadyError
    return processor


def get_knowledge_management_service(request: Request) -> KnowledgeManagementService:
    service = request.app.state.dependencies.knowledge_management_service
    if service is None:
        raise KnowledgeNotConfiguredError("Knowledge management is not configured")
    return service
