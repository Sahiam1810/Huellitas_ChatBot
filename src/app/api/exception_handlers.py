from dataclasses import dataclass

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.api.schemas.health import ProblemDetail
from app.api.schemas.responses import MessageProblemDetail
from app.shared.exceptions import (
    ChatModelError,
    ModelAuthenticationError,
    ModelConfigurationError,
    ModelInvalidResponseError,
    ModelRateLimitError,
    ModelRequestError,
    ModelTimeoutError,
    ModelUnavailableError,
    ServiceNotReadyError,
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


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceNotReadyError, service_not_ready_handler)
    app.add_exception_handler(RequestValidationError, request_validation_handler)
    for error_type in MODEL_PROBLEMS:
        app.add_exception_handler(error_type, chat_model_error_handler)
