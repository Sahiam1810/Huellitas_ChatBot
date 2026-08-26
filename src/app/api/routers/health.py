from fastapi import APIRouter, Request

from app.api.schemas.health import HealthResponse, ProblemDetail
from app.shared.exceptions import ServiceNotReadyError, VectorStoreUnavailableError

router = APIRouter(prefix="/health", tags=["Health"])


@router.get(
    "/live",
    response_model=HealthResponse,
    summary="Check whether the process is alive",
)
async def live() -> HealthResponse:
    return HealthResponse(status="alive")


@router.get(
    "/ready",
    response_model=HealthResponse,
    responses={
        503: {
            "model": ProblemDetail,
            "description": "The application has not completed startup or is shutting down.",
        }
    },
    summary="Check whether the application is ready",
)
async def ready(request: Request) -> HealthResponse:
    if not request.app.state.ready or not request.app.state.rag_collections_ready:
        raise ServiceNotReadyError

    vector_store = request.app.state.dependencies.vector_store
    if vector_store is not None:
        try:
            await vector_store.check_health()
        except VectorStoreUnavailableError:
            raise ServiceNotReadyError from None
    return HealthResponse(status="ready")
