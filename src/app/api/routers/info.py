from fastapi import APIRouter, Request

from app.api.schemas.info import ServiceInfoResponse

router = APIRouter(prefix="/info", tags=["Service"])


@router.get(
    "",
    response_model=ServiceInfoResponse,
    summary="Get safe service metadata",
)
async def info(request: Request) -> ServiceInfoResponse:
    settings = request.app.state.settings
    return ServiceInfoResponse(
        name=settings.app_name,
        version=settings.app_version,
        environment=settings.environment,
    )
