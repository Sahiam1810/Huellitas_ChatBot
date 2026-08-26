from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.orchestration.conversation_memory_writer import ConversationMemoryWriter
from app.ports.global_knowledge_store import GlobalKnowledgeKind
from app.shared.exceptions import VectorStoreUnavailableError

CONVERSATION_ID = UUID("bda5a441-e907-4781-bca6-44c25a73255a")
PRIVATE_POINT_ID = UUID("9ba62b92-f8f4-40b4-8fb4-19696b288184")
GLOBAL_DOCUMENT_ID = UUID("55af1547-6e88-467c-8c60-cbeb1e5e704e")
NOW = datetime(2026, 8, 26, 12, 30, tzinfo=UTC)
QUERY_VECTOR = (0.1, 0.2, 0.3)


def make_writer(
    *,
    memory: object | None = None,
    global_store: object | None = None,
) -> tuple[ConversationMemoryWriter, object, object]:
    memory = memory or SimpleNamespace(remember=AsyncMock(return_value=None))
    global_store = global_store or SimpleNamespace(upsert_global=AsyncMock(return_value=None))
    identifiers = iter((PRIVATE_POINT_ID, GLOBAL_DOCUMENT_ID))
    writer = ConversationMemoryWriter(
        memory,
        global_store,
        uuid_factory=lambda: next(identifiers),
        clock=lambda: NOW,
    )
    return writer, memory, global_store


@pytest.mark.anyio
async def test_writer_stores_private_memory_with_exact_scope_and_query_vector() -> None:
    writer, memory, global_store = make_writer()

    result = await writer.write(
        conversation_id=CONVERSATION_ID,
        question="Pregunta",
        answer="Respuesta",
        query_vector=QUERY_VECTOR,
        publish_as_global_knowledge=False,
    )

    record = memory.remember.await_args.args[0]
    assert record.point_id == PRIVATE_POINT_ID
    assert record.conversation_id == CONVERSATION_ID
    assert record.vector == QUERY_VECTOR
    assert record.question == "Pregunta"
    assert record.answer == "Respuesta"
    assert record.created_at == NOW
    global_store.upsert_global.assert_not_awaited()
    assert result.memory_stored is True
    assert result.knowledge_published is False
    assert result.degraded is False


@pytest.mark.anyio
async def test_writer_publishes_approved_exchange_only_with_explicit_approval() -> None:
    writer, memory, global_store = make_writer()

    result = await writer.write(
        conversation_id=CONVERSATION_ID,
        question="Pregunta",
        answer="Respuesta",
        query_vector=QUERY_VECTOR,
        publish_as_global_knowledge=True,
    )

    memory.remember.assert_awaited_once()
    records = global_store.upsert_global.await_args.args[0]
    assert len(records) == 1
    record = records[0]
    assert record.point_id == GLOBAL_DOCUMENT_ID
    assert record.document_id == GLOBAL_DOCUMENT_ID
    assert record.external_id == f"approved-exchange:{GLOBAL_DOCUMENT_ID}"
    assert record.vector == QUERY_VECTOR
    assert record.kind is GlobalKnowledgeKind.APPROVED_EXCHANGE
    assert record.content == "Question:\nPregunta\n\nAnswer:\nRespuesta"
    assert record.title == "Approved conversation exchange"
    assert record.source == "messages"
    assert record.tags == ("approved_exchange",)
    assert record.version == 1
    assert record.chunk_index == 0
    assert record.active is True
    assert record.deleted is False
    assert record.created_at == NOW
    assert record.updated_at == NOW
    assert result.memory_stored is True
    assert result.knowledge_published is True
    assert result.degraded is False


@pytest.mark.anyio
async def test_private_failure_does_not_prevent_approved_global_publication() -> None:
    memory = SimpleNamespace(
        remember=AsyncMock(side_effect=VectorStoreUnavailableError("qdrant secret"))
    )
    writer, _, global_store = make_writer(memory=memory)

    result = await writer.write(
        conversation_id=CONVERSATION_ID,
        question="Pregunta",
        answer="Respuesta",
        query_vector=QUERY_VECTOR,
        publish_as_global_knowledge=True,
    )

    global_store.upsert_global.assert_awaited_once()
    assert result.memory_stored is False
    assert result.knowledge_published is True
    assert result.degraded is True


@pytest.mark.anyio
async def test_global_failure_preserves_private_memory_result() -> None:
    global_store = SimpleNamespace(
        upsert_global=AsyncMock(side_effect=VectorStoreUnavailableError("qdrant secret"))
    )
    writer, memory, _ = make_writer(global_store=global_store)

    result = await writer.write(
        conversation_id=CONVERSATION_ID,
        question="Pregunta",
        answer="Respuesta",
        query_vector=QUERY_VECTOR,
        publish_as_global_knowledge=True,
    )

    memory.remember.assert_awaited_once()
    assert result.memory_stored is True
    assert result.knowledge_published is False
    assert result.degraded is True


@pytest.mark.anyio
async def test_unexpected_write_error_propagates() -> None:
    memory = SimpleNamespace(remember=AsyncMock(side_effect=RuntimeError("bug")))
    writer, _, _ = make_writer(memory=memory)

    with pytest.raises(RuntimeError, match="bug"):
        await writer.write(
            conversation_id=CONVERSATION_ID,
            question="Pregunta",
            answer="Respuesta",
            query_vector=QUERY_VECTOR,
            publish_as_global_knowledge=False,
        )
