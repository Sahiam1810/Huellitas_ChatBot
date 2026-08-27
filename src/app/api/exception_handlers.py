from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas.health import ProblemDetail
from app.api.schemas.responses import MessageProblemDetail
from app.shared.exceptions import (
    AuthenticationError,
    AuthenticationRequiredError,
    AuthorizationError,
    ChatModelError,
    EmbeddingAuthenticationError,
    EmbeddingConfigurationError,
    EmbeddingInvalidResponseError,
    EmbeddingModelError,
    EmbeddingRateLimitError,
    EmbeddingRequestError,
    EmbeddingTimeoutError,
    EmbeddingUnavailableError,
    IdempotencyCapacityExceededError,
    IdempotencyError,
    IdempotencyKeyConflictError,
    IdentityMismatchError,
    InsufficientPermissionsError,
    InvalidAccessTokenError,
    KnowledgeDocumentConsistencyError,
    KnowledgeDocumentDeletedError,
    KnowledgeDocumentNotFoundError,
    KnowledgeError,
    KnowledgeExternalIdConflictError,
    KnowledgeNotConfiguredError,
    ModelAuthenticationError,
    ModelConfigurationError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
    ServiceNotReadyError,
    VectorStoreConfigurationError,
    VectorStoreError,
    VectorStoreInvalidResponseError,
    VectorStoreUnavailableError,
)


@dataclass(frozen=True, slots=True)
class ProblemSpec:
    title: str
    status: int
    detail: str
    code: str


MODEL_PROBLEMS: dict[type[ChatModelError], ProblemSpec] = {
    ModelConfigurationError: ProblemSpec(
        title="Service Unavailable",
        status=503,
        detail="Chat model is not configured",
        code="model_not_configured",
    ),
    ModelAuthenticationError: ProblemSpec(
        title="Bad Gateway",
        status=502,
        detail="Provider authentication failed",
        code="provider_authentication_failed",
    ),
    ModelRateLimitError: ProblemSpec(
        title="Service Unavailable",
        status=503,
        detail="Provider rate limit reached",
        code="provider_rate_limited",
    ),
    ModelTimeoutError: ProblemSpec(
        title="Gateway Timeout",
        status=504,
        detail="Provider request timed out",
        code="provider_timeout",
    ),
    ModelUnavailableError: ProblemSpec(
        title="Service Unavailable",
        status=503,
        detail="Provider is unavailable",
        code="provider_unavailable",
    ),
    ModelRequestError: ProblemSpec(
        title="Bad Gateway",
        status=502,
        detail="Provider rejected the request",
        code="provider_request_rejected",
    ),
    ModelInvalidResponseError: ProblemSpec(
        title="Bad Gateway",
        status=502,
        detail="Provider returned an invalid response",
        code="provider_invalid_response",
    ),
}

KNOWLEDGE_PROBLEMS: dict[type[KnowledgeError], ProblemSpec] = {
    KnowledgeNotConfiguredError: ProblemSpec(
        "Service Unavailable",
        503,
        "Knowledge management is not configured",
        "knowledge_not_configured",
    ),
    KnowledgeDocumentNotFoundError: ProblemSpec(
        "Not Found", 404, "Knowledge document was not found", "knowledge_document_not_found"
    ),
    KnowledgeExternalIdConflictError: ProblemSpec(
        "Conflict", 409, "Knowledge external ID is already in use", "knowledge_external_id_conflict"
    ),
    KnowledgeDocumentDeletedError: ProblemSpec(
        "Conflict", 409, "Knowledge document is deleted", "knowledge_document_deleted"
    ),
    KnowledgeDocumentConsistencyError: ProblemSpec(
        "Service Unavailable",
        503,
        "Knowledge document state is inconsistent",
        "knowledge_document_inconsistent",
    ),
}

EMBEDDING_PROBLEMS: dict[type[EmbeddingModelError], ProblemSpec] = {
    EmbeddingConfigurationError: ProblemSpec(
        "Service Unavailable", 503, "Embedding model is not configured", "embedding_not_configured"
    ),
    EmbeddingAuthenticationError: ProblemSpec(
        "Bad Gateway", 502, "Embedding authentication failed", "embedding_authentication_failed"
    ),
    EmbeddingRateLimitError: ProblemSpec(
        "Service Unavailable", 503, "Embedding rate limit reached", "embedding_rate_limited"
    ),
    EmbeddingTimeoutError: ProblemSpec(
        "Gateway Timeout", 504, "Embedding request timed out", "embedding_timeout"
    ),
    EmbeddingUnavailableError: ProblemSpec(
        "Service Unavailable", 503, "Embedding provider is unavailable", "embedding_unavailable"
    ),
    EmbeddingRequestError: ProblemSpec(
        "Bad Gateway", 502, "Embedding provider rejected the request", "embedding_request_rejected"
    ),
    EmbeddingInvalidResponseError: ProblemSpec(
        "Bad Gateway",
        502,
        "Embedding provider returned an invalid response",
        "embedding_invalid_response",
    ),
}

VECTOR_PROBLEMS: dict[type[VectorStoreError], ProblemSpec] = {
    VectorStoreConfigurationError: ProblemSpec(
        "Service Unavailable", 503, "Vector store is not configured", "vector_store_not_configured"
    ),
    VectorStoreUnavailableError: ProblemSpec(
        "Service Unavailable", 503, "Vector store is unavailable", "vector_store_unavailable"
    ),
    VectorStoreInvalidResponseError: ProblemSpec(
        "Bad Gateway",
        502,
        "Vector store returned an invalid response",
        "vector_store_invalid_response",
    ),
}

IDEMPOTENCY_PROBLEMS: dict[type[IdempotencyError], ProblemSpec] = {
    IdempotencyKeyConflictError: ProblemSpec(
        "Conflict",
        409,
        "Idempotency key was already used with a different request",
        "idempotency_key_conflict",
    ),
    IdempotencyCapacityExceededError: ProblemSpec(
        "Service Unavailable",
        503,
        "Idempotency capacity is temporarily exhausted",
        "idempotency_capacity_exceeded",
    ),
}

AUTHENTICATION_PROBLEMS: dict[type[AuthenticationError], ProblemSpec] = {
    AuthenticationRequiredError: ProblemSpec(
        "Unauthorized", 401, "Authentication is required", "authentication_required"
    ),
    InvalidAccessTokenError: ProblemSpec(
        "Unauthorized", 401, "Access token is invalid", "invalid_access_token"
    ),
}

AUTHORIZATION_PROBLEMS: dict[type[AuthorizationError], ProblemSpec] = {
    IdentityMismatchError: ProblemSpec(
        "Forbidden",
        403,
        "Authenticated identity does not match the request",
        "identity_mismatch",
    ),
    InsufficientPermissionsError: ProblemSpec(
        "Forbidden",
        403,
        "Authenticated role does not have sufficient permissions",
        "insufficient_permissions",
    ),
}


def problem_response(problem: MessageProblemDetail) -> JSONResponse:
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


async def service_not_ready_handler(
    request: Request,
    _: ServiceNotReadyError,
) -> JSONResponse:
    problem = ProblemDetail(
        title="Service Unavailable",
        status=503,
        detail="Application is not ready",
        instance=request.url.path,
    )
    return JSONResponse(
        status_code=problem.status,
        content=problem.model_dump(),
        media_type="application/problem+json",
    )


async def request_validation_handler(
    request: Request,
    _: RequestValidationError,
) -> JSONResponse:
    return problem_response(
        MessageProblemDetail(
            title="Unprocessable Entity",
            status=422,
            detail="Request validation failed",
            instance=request.url.path,
            code="invalid_request",
        )
    )


async def chat_model_error_handler(
    request: Request,
    error: ChatModelError,
) -> JSONResponse:
    spec = MODEL_PROBLEMS[type(error)]
    return problem_response(
        MessageProblemDetail(
            title=spec.title,
            status=spec.status,
            detail=spec.detail,
            instance=request.url.path,
            code=spec.code,
        )
    )


async def dependency_error_handler(
    request: Request,
    error: KnowledgeError | EmbeddingModelError | VectorStoreError,
) -> JSONResponse:
    problems = {**KNOWLEDGE_PROBLEMS, **EMBEDDING_PROBLEMS, **VECTOR_PROBLEMS}
    spec = problems[type(error)]
    return problem_response(
        MessageProblemDetail(
            title=spec.title,
            status=spec.status,
            detail=spec.detail,
            instance=request.url.path,
            code=spec.code,
        )
    )


async def idempotency_error_handler(
    request: Request,
    error: IdempotencyError,
) -> JSONResponse:
    spec = IDEMPOTENCY_PROBLEMS[type(error)]
    return problem_response(
        MessageProblemDetail(
            title=spec.title,
            status=spec.status,
            detail=spec.detail,
            instance=request.url.path,
            code=spec.code,
        )
    )


async def authentication_error_handler(
    request: Request,
    error: AuthenticationError,
) -> JSONResponse:
    spec = AUTHENTICATION_PROBLEMS[type(error)]
    response = problem_response(
        MessageProblemDetail(
            title=spec.title,
            status=spec.status,
            detail=spec.detail,
            instance=request.url.path,
            code=spec.code,
        )
    )
    response.headers["WWW-Authenticate"] = "Bearer"
    return response


async def authorization_error_handler(
    request: Request,
    error: AuthorizationError,
) -> JSONResponse:
    spec = AUTHORIZATION_PROBLEMS[type(error)]
    return problem_response(
        MessageProblemDetail(
            title=spec.title,
            status=spec.status,
            detail=spec.detail,
            instance=request.url.path,
            code=spec.code,
        )
    )


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceNotReadyError, service_not_ready_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    for error_type in MODEL_PROBLEMS:
        app.add_exception_handler(error_type, chat_model_error_handler)
    for error_type in (*KNOWLEDGE_PROBLEMS, *EMBEDDING_PROBLEMS, *VECTOR_PROBLEMS):
        app.add_exception_handler(error_type, dependency_error_handler)
    for error_type in IDEMPOTENCY_PROBLEMS:
        app.add_exception_handler(error_type, idempotency_error_handler)
    for error_type in AUTHENTICATION_PROBLEMS:
        app.add_exception_handler(error_type, authentication_error_handler)
    for error_type in AUTHORIZATION_PROBLEMS:
        app.add_exception_handler(error_type, authorization_error_handler)
