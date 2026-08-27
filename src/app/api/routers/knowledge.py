from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Path, Query, Response, Security, status

from app.api.dependencies import (
    get_knowledge_management_service,
    require_knowledge_administrator,
)
from app.api.schemas.knowledge import (
    CreateKnowledgeDocumentRequest,
    KnowledgeDocumentPageResponse,
    KnowledgeDocumentResponse,
    ReplaceKnowledgeDocumentRequest,
    SetKnowledgeDocumentStatusRequest,
)
from app.api.schemas.responses import MessageProblemDetail
from app.knowledge.contracts import (
    CreateKnowledgeDocument,
    KnowledgeDocumentFilters,
    ReplaceKnowledgeDocument,
)
from app.knowledge.management_service import KnowledgeManagementService

router = APIRouter(
    prefix="/knowledge/documents",
    tags=["Knowledge"],
    dependencies=[Security(require_knowledge_administrator)],
)

ERROR_RESPONSES = {
    401: {"model": MessageProblemDetail, "description": "Authentication is required."},
    403: {"model": MessageProblemDetail, "description": "Administrator role is required."},
    404: {"model": MessageProblemDetail, "description": "Document not found."},
    409: {"model": MessageProblemDetail, "description": "Document state conflict."},
    422: {"model": MessageProblemDetail, "description": "Invalid document request."},
    502: {"model": MessageProblemDetail, "description": "Dependency returned an invalid response."},
    503: {"model": MessageProblemDetail, "description": "Knowledge service is unavailable."},
    504: {"model": MessageProblemDetail, "description": "Embedding request timed out."},
}

KnowledgeService = Annotated[KnowledgeManagementService, Depends(get_knowledge_management_service)]
DocumentId = Annotated[UUID, Path(alias="documentId")]


@router.post(
    "",
    response_model=KnowledgeDocumentResponse,
    status_code=status.HTTP_201_CREATED,
    responses=ERROR_RESPONSES,
    summary="Register a global knowledge document",
)
async def create_document(
    payload: CreateKnowledgeDocumentRequest, service: KnowledgeService
) -> KnowledgeDocumentResponse:
    document = await service.create(
        CreateKnowledgeDocument(
            external_id=payload.external_id,
            title=payload.title,
            content=payload.content,
            source=payload.source,
            tags=tuple(payload.tags),
            active=payload.active,
        )
    )
    return KnowledgeDocumentResponse.from_document(document)


@router.get(
    "",
    response_model=KnowledgeDocumentPageResponse,
    responses=ERROR_RESPONSES,
    summary="List global knowledge documents",
)
async def list_documents(
    service: KnowledgeService,
    limit: Annotated[int, Query(ge=1, le=100)] = 20,
    cursor: str | None = None,
    active: bool | None = None,
    include_deleted: Annotated[bool, Query(alias="includeDeleted")] = False,
    source: str | None = None,
    tags: Annotated[list[str] | None, Query()] = None,
) -> KnowledgeDocumentPageResponse:
    page = await service.list(
        KnowledgeDocumentFilters(
            limit=limit,
            cursor=cursor,
            active=active,
            include_deleted=include_deleted,
            source=source,
            tags=tuple(tags or ()),
        )
    )
    return KnowledgeDocumentPageResponse.from_page(page)


@router.get(
    "/{documentId}",
    response_model=KnowledgeDocumentResponse,
    responses=ERROR_RESPONSES,
    summary="Get a global knowledge document",
)
async def get_document(
    document_id: DocumentId,
    service: KnowledgeService,
    include_deleted: Annotated[bool, Query(alias="includeDeleted")] = False,
) -> KnowledgeDocumentResponse:
    document = await service.get(document_id, include_deleted=include_deleted)
    return KnowledgeDocumentResponse.from_document(document)


@router.put(
    "/{documentId}",
    response_model=KnowledgeDocumentResponse,
    responses=ERROR_RESPONSES,
    summary="Replace a global knowledge document",
)
async def replace_document(
    document_id: DocumentId,
    payload: ReplaceKnowledgeDocumentRequest,
    service: KnowledgeService,
) -> KnowledgeDocumentResponse:
    document = await service.replace(
        document_id,
        ReplaceKnowledgeDocument(
            title=payload.title,
            content=payload.content,
            source=payload.source,
            tags=tuple(payload.tags),
            active=payload.active,
        ),
    )
    return KnowledgeDocumentResponse.from_document(document)


@router.patch(
    "/{documentId}/status",
    response_model=KnowledgeDocumentResponse,
    responses=ERROR_RESPONSES,
    summary="Activate or deactivate a knowledge document",
)
async def set_document_status(
    document_id: DocumentId,
    payload: SetKnowledgeDocumentStatusRequest,
    service: KnowledgeService,
) -> KnowledgeDocumentResponse:
    document = await service.set_active(document_id, payload.active)
    return KnowledgeDocumentResponse.from_document(document)


@router.delete(
    "/{documentId}",
    status_code=status.HTTP_204_NO_CONTENT,
    response_class=Response,
    responses=ERROR_RESPONSES,
    summary="Logically delete a knowledge document",
)
async def delete_document(document_id: DocumentId, service: KnowledgeService) -> Response:
    await service.delete(document_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/{documentId}/restore",
    response_model=KnowledgeDocumentResponse,
    responses=ERROR_RESPONSES,
    summary="Restore a knowledge document as inactive",
)
async def restore_document(
    document_id: DocumentId, service: KnowledgeService
) -> KnowledgeDocumentResponse:
    document = await service.restore(document_id)
    return KnowledgeDocumentResponse.from_document(document)
