from datetime import datetime
from typing import Annotated
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StringConstraints

from app.ports.global_knowledge_store import (
    GlobalKnowledgeDocument,
    GlobalKnowledgeDocumentPage,
)

NonBlankText = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1)]


class CreateKnowledgeDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    external_id: NonBlankText = Field(alias="externalId")
    title: NonBlankText
    content: NonBlankText
    source: NonBlankText
    tags: list[NonBlankText]
    active: bool


class ReplaceKnowledgeDocumentRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: NonBlankText
    content: NonBlankText
    source: NonBlankText
    tags: list[NonBlankText]
    active: bool


class SetKnowledgeDocumentStatusRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    active: bool


class KnowledgeDocumentResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    document_id: UUID = Field(alias="documentId")
    external_id: str = Field(alias="externalId")
    version: int = Field(ge=1)
    content: str
    title: str
    source: str
    tags: list[str]
    chunk_count: int = Field(alias="chunkCount", ge=1)
    active: bool
    deleted: bool
    created_at: datetime = Field(alias="createdAt")
    updated_at: datetime = Field(alias="updatedAt")

    @classmethod
    def from_document(cls, document: GlobalKnowledgeDocument) -> "KnowledgeDocumentResponse":
        return cls(
            document_id=document.document_id,
            external_id=document.external_id,
            version=document.version,
            content=document.content,
            title=document.title,
            source=document.source,
            tags=list(document.tags),
            chunk_count=document.chunk_count,
            active=document.active,
            deleted=document.deleted,
            created_at=document.created_at,
            updated_at=document.updated_at,
        )


class KnowledgeDocumentPageResponse(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    documents: list[KnowledgeDocumentResponse]
    next_cursor: str | None = Field(alias="nextCursor")

    @classmethod
    def from_page(cls, page: GlobalKnowledgeDocumentPage) -> "KnowledgeDocumentPageResponse":
        return cls(
            documents=[KnowledgeDocumentResponse.from_document(item) for item in page.documents],
            next_cursor=page.next_cursor,
        )
