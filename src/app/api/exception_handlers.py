from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.api.schemas.health import ProblemDetail
from app.shared.exceptions import ServiceNotReadyError


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


def register_exception_handlers(app: FastAPI) -> None:
    app.add_exception_handler(ServiceNotReadyError, service_not_ready_handler)
