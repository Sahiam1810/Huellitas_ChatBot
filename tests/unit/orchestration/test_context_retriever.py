import asyncio
from types import SimpleNamespace
from unittest.mock import AsyncMock
from uuid import UUID

import pytest

from app.orchestration.context_retriever import ContextRetriever
from app.orchestration.rag_contracts import RagStatus, SemanticRoute
from app.orchestration.semantic_routing_policy import SemanticRoutingPolicy
from app.ports.conversation_memory_store import ConversationMemoryMatch
from app.ports.embedding_model import (
    EmbeddingProvider,
    EmbeddingResponse,
    EmbeddingUsage,
    EmbeddingVector,
)
from app.ports.global_knowledge_store import GlobalKnowledgeKind, GlobalKnowledgeMatch
from app.shared.exceptions import EmbeddingUnavailableError, VectorStoreUnavailableError

CONVERSATION_ID = UUID("bda5a441-e907-4781-bca6-44c25a73255a")
GLOBAL_POINT_ID = UUID("40c2580b-e2f4-4323-9d27-51b4dfbfc7ab")
GLOBAL_DOCUMENT_ID = UUID("55af1547-6e88-467c-8c60-cbeb1e5e704e")
MEMORY_POINT_ID = UUID("9ba62b92-f8f4-40b4-8fb4-19696b288184")
QUERY_VECTOR = (0.1, 0.2, 0.3)


def embedding_response() -> EmbeddingResponse:
    return EmbeddingResponse(
        vectors=(EmbeddingVector(QUERY_VECTOR),),
        provider=EmbeddingProvider.OPENAI,
        model="embedding-test",
        usage=EmbeddingUsage(input_tokens=4, total_tokens=4),
    )


def global_match(
    content: str = "Las vacunas deben seguir el plan veterinario.",
    *,
    score: float = 0.91,
    kind: GlobalKnowledgeKind = GlobalKnowledgeKind.DOCUMENT_CHUNK,
) -> GlobalKnowledgeMatch:
    return GlobalKnowledgeMatch(
        point_id=GLOBAL_POINT_ID,
        score=score,
        content=content,
        document_id=GLOBAL_DOCUMENT_ID,
        title="Guía preventiva",
        source="manual",
        kind=kind,
    )


def memory_match(*, score: float = 0.87) -> ConversationMemoryMatch:
    return ConversationMemoryMatch(
        point_id=MEMORY_POINT_ID,
        score=score,
        question="¿Qué edad tiene Luna?",
        answer="Luna tiene dos años.",
    )


def make_retriever(
    *,
    embedding: object | None = None,
    global_store: object | None = None,
    memory_store: object | None = None,
    max_context_characters: int = 6000,
    semantic_routing_policy: SemanticRoutingPolicy | None = None,
) -> tuple[ContextRetriever, object, object, object]:
    embedding = embedding or SimpleNamespace(
        embed_query=AsyncMock(return_value=embedding_response())
    )
    global_store = global_store or SimpleNamespace(
        search_global=AsyncMock(return_value=(global_match(),))
    )
    memory_store = memory_store or SimpleNamespace(
        search_conversation=AsyncMock(return_value=(memory_match(),))
    )
    return (
        ContextRetriever(
            embedding,
            global_store,
            memory_store,
            global_limit=4,
            conversation_limit=3,
            score_threshold=0.7,
            max_context_characters=max_context_characters,
            semantic_routing_policy=semantic_routing_policy,
        ),
        embedding,
        global_store,
        memory_store,
    )


@pytest.mark.anyio
async def test_retriever_embeds_once_and_scopes_memory_query_to_conversation() -> None:
    retriever, embedding, global_store, memory_store = make_retriever()

    result = await retriever.retrieve("¿Cuándo vacuno a Luna?", CONVERSATION_ID)

    embedding.embed_query.assert_awaited_once_with("¿Cuándo vacuno a Luna?")
    global_query = global_store.search_global.await_args.args[0]
    assert global_query.vector == QUERY_VECTOR
    assert global_query.limit == 4
    assert global_query.score_threshold == 0.7
    memory_query = memory_store.search_conversation.await_args.args[0]
    assert memory_query.conversation_id == CONVERSATION_ID
    assert memory_query.vector == QUERY_VECTOR
    assert memory_query.limit == 3
    assert memory_query.score_threshold == 0.7
    assert result.status is RagStatus.USED
    assert result.query_vector == QUERY_VECTOR
    assert result.global_matches == 1
    assert result.conversation_matches == 1
    assert result.route is SemanticRoute.DISABLED
    assert result.top_score is None


@pytest.mark.anyio
async def test_semantic_retriever_uses_one_unfiltered_parallel_search_per_scope() -> None:
    policy = SemanticRoutingPolicy(high_threshold=0.95, medium_threshold=0.80)
    retriever, embedding, global_store, memory_store = make_retriever(
        semantic_routing_policy=policy
    )

    await retriever.retrieve("¿Cuándo vacuno a Luna?", CONVERSATION_ID)

    embedding.embed_query.assert_awaited_once_with("¿Cuándo vacuno a Luna?")
    global_store.search_global.assert_awaited_once()
    memory_store.search_conversation.assert_awaited_once()
    assert global_store.search_global.await_args.args[0].score_threshold is None
    assert memory_store.search_conversation.await_args.args[0].score_threshold is None


@pytest.mark.anyio
async def test_high_private_memory_returns_direct_route_without_prompt() -> None:
    policy = SemanticRoutingPolicy(high_threshold=0.95, medium_threshold=0.80)
    retriever, _, _, _ = make_retriever(
        global_store=SimpleNamespace(search_global=AsyncMock(return_value=())),
        memory_store=SimpleNamespace(
            search_conversation=AsyncMock(return_value=(memory_match(score=0.97),))
        ),
        semantic_routing_policy=policy,
    )

    result = await retriever.retrieve("¿Qué edad tiene Luna?", CONVERSATION_ID)

    assert result.status is RagStatus.USED
    assert result.route is SemanticRoute.DIRECT
    assert result.direct_answer == "Luna tiene dos años."
    assert result.prompt_context is None
    assert result.top_score == 0.97


@pytest.mark.anyio
async def test_high_document_remains_contextual() -> None:
    policy = SemanticRoutingPolicy(high_threshold=0.95, medium_threshold=0.80)
    retriever, _, _, _ = make_retriever(
        global_store=SimpleNamespace(
            search_global=AsyncMock(return_value=(global_match(score=0.99),))
        ),
        memory_store=SimpleNamespace(search_conversation=AsyncMock(return_value=())),
        semantic_routing_policy=policy,
    )

    result = await retriever.retrieve("Pregunta", CONVERSATION_ID)

    assert result.route is SemanticRoute.CONTEXTUAL
    assert result.direct_answer is None
    assert result.prompt_context is not None
    assert "Las vacunas" in result.prompt_context
    assert result.top_score == 0.99


@pytest.mark.anyio
async def test_low_similarity_uses_general_route_without_prompt_context() -> None:
    policy = SemanticRoutingPolicy(high_threshold=0.95, medium_threshold=0.80)
    retriever, _, _, _ = make_retriever(
        global_store=SimpleNamespace(
            search_global=AsyncMock(return_value=(global_match(score=0.79),))
        ),
        memory_store=SimpleNamespace(
            search_conversation=AsyncMock(return_value=(memory_match(score=0.70),))
        ),
        semantic_routing_policy=policy,
    )

    result = await retriever.retrieve("Pregunta", CONVERSATION_ID)

    assert result.status is RagStatus.EMPTY
    assert result.route is SemanticRoute.GENERAL
    assert result.prompt_context is None
    assert result.top_score == 0.79


@pytest.mark.anyio
async def test_retriever_can_disable_direct_route_for_explicit_publication() -> None:
    policy = SemanticRoutingPolicy(high_threshold=0.95, medium_threshold=0.80)
    retriever, _, _, _ = make_retriever(
        global_store=SimpleNamespace(search_global=AsyncMock(return_value=())),
        memory_store=SimpleNamespace(
            search_conversation=AsyncMock(return_value=(memory_match(score=0.97),))
        ),
        semantic_routing_policy=policy,
    )

    result = await retriever.retrieve("Pregunta", CONVERSATION_ID, allow_direct=False)

    assert result.route is SemanticRoute.CONTEXTUAL
    assert result.direct_answer is None
    assert result.prompt_context is not None


@pytest.mark.anyio
async def test_partial_failure_suppresses_direct_route_and_keeps_safe_context() -> None:
    policy = SemanticRoutingPolicy(high_threshold=0.95, medium_threshold=0.80)
    retriever, _, _, _ = make_retriever(
        global_store=SimpleNamespace(
            search_global=AsyncMock(side_effect=VectorStoreUnavailableError("secret"))
        ),
        memory_store=SimpleNamespace(
            search_conversation=AsyncMock(return_value=(memory_match(score=0.99),))
        ),
        semantic_routing_policy=policy,
    )

    result = await retriever.retrieve("Pregunta", CONVERSATION_ID)

    assert result.status is RagStatus.DEGRADED
    assert result.route is SemanticRoute.DEGRADED
    assert result.direct_answer is None
    assert result.prompt_context is not None
    assert "Luna tiene dos años." in result.prompt_context


@pytest.mark.anyio
async def test_retriever_runs_global_and_conversation_searches_concurrently() -> None:
    started: set[str] = set()
    both_started = asyncio.Event()

    async def global_search(query: object) -> tuple[GlobalKnowledgeMatch, ...]:
        started.add("global")
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=0.5)
        return (global_match(),)

    async def memory_search(query: object) -> tuple[ConversationMemoryMatch, ...]:
        started.add("memory")
        if len(started) == 2:
            both_started.set()
        await asyncio.wait_for(both_started.wait(), timeout=0.5)
        return (memory_match(),)

    retriever, _, _, _ = make_retriever(
        global_store=SimpleNamespace(search_global=global_search),
        memory_store=SimpleNamespace(search_conversation=memory_search),
    )

    result = await retriever.retrieve("Pregunta", CONVERSATION_ID)

    assert started == {"global", "memory"}
    assert result.status is RagStatus.USED


@pytest.mark.anyio
async def test_retriever_reports_empty_without_prompt_context() -> None:
    retriever, _, _, _ = make_retriever(
        global_store=SimpleNamespace(search_global=AsyncMock(return_value=())),
        memory_store=SimpleNamespace(search_conversation=AsyncMock(return_value=())),
    )

    result = await retriever.retrieve("Pregunta", CONVERSATION_ID)

    assert result.status is RagStatus.EMPTY
    assert result.prompt_context is None
    assert result.query_vector == QUERY_VECTOR


@pytest.mark.anyio
async def test_embedding_failure_degrades_without_searching() -> None:
    embedding = SimpleNamespace(
        embed_query=AsyncMock(side_effect=EmbeddingUnavailableError("provider secret"))
    )
    retriever, _, global_store, memory_store = make_retriever(embedding=embedding)

    result = await retriever.retrieve("Pregunta", CONVERSATION_ID)

    assert result.status is RagStatus.DEGRADED
    assert result.query_vector is None
    assert result.prompt_context is None
    global_store.search_global.assert_not_awaited()
    memory_store.search_conversation.assert_not_awaited()


@pytest.mark.anyio
async def test_one_store_failure_keeps_other_context_and_marks_degraded() -> None:
    global_store = SimpleNamespace(
        search_global=AsyncMock(side_effect=VectorStoreUnavailableError("qdrant secret"))
    )
    retriever, _, _, _ = make_retriever(global_store=global_store)

    result = await retriever.retrieve("Pregunta", CONVERSATION_ID)

    assert result.status is RagStatus.DEGRADED
    assert result.global_matches == 0
    assert result.conversation_matches == 1
    assert result.prompt_context is not None
    assert "<conversation_memory>" in result.prompt_context
    assert "Luna tiene dos años." in result.prompt_context


@pytest.mark.anyio
async def test_unexpected_embedding_and_store_errors_propagate() -> None:
    embedding = SimpleNamespace(embed_query=AsyncMock(side_effect=RuntimeError("bug")))
    retriever, _, _, _ = make_retriever(embedding=embedding)

    with pytest.raises(RuntimeError, match="bug"):
        await retriever.retrieve("Pregunta", CONVERSATION_ID)

    global_store = SimpleNamespace(search_global=AsyncMock(side_effect=RuntimeError("bug")))
    retriever, _, _, _ = make_retriever(global_store=global_store)

    with pytest.raises(RuntimeError, match="bug"):
        await retriever.retrieve("Pregunta", CONVERSATION_ID)


@pytest.mark.anyio
async def test_prompt_context_separates_global_knowledge_before_private_memory() -> None:
    retriever, _, _, _ = make_retriever()

    result = await retriever.retrieve("Pregunta", CONVERSATION_ID)

    assert result.prompt_context is not None
    assert result.prompt_context.index("<global_knowledge>") < result.prompt_context.index(
        "<conversation_memory>"
    )
    assert "[manual | Guía preventiva]" in result.prompt_context
    assert "User: ¿Qué edad tiene Luna?" in result.prompt_context
    assert "Assistant: Luna tiene dos años." in result.prompt_context


@pytest.mark.anyio
async def test_prompt_context_never_exceeds_character_budget() -> None:
    retriever, _, _, _ = make_retriever(
        global_store=SimpleNamespace(
            search_global=AsyncMock(return_value=(global_match("x" * 1000),))
        ),
        memory_store=SimpleNamespace(search_conversation=AsyncMock(return_value=())),
        max_context_characters=500,
    )

    result = await retriever.retrieve("Pregunta", CONVERSATION_ID)

    assert result.prompt_context is not None
    assert len(result.prompt_context) <= 500
    assert result.prompt_context.startswith("<global_knowledge>")
    assert result.prompt_context.endswith("</global_knowledge>")
