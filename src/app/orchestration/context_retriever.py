import asyncio
import logging
from collections.abc import Sequence
from html import escape
from uuid import UUID

from app.orchestration.rag_contracts import RagStatus, RetrievedRagContext, SemanticRoute
from app.orchestration.semantic_routing_policy import SemanticRoutingPolicy
from app.ports.conversation_memory_store import (
    ConversationMemoryMatch,
    ConversationMemoryQuery,
    ConversationMemoryStore,
)
from app.ports.embedding_model import EmbeddingModel
from app.ports.global_knowledge_store import (
    GlobalKnowledgeMatch,
    GlobalKnowledgeQuery,
    GlobalKnowledgeStore,
)
from app.shared.exceptions import EmbeddingModelError, VectorStoreError

logger = logging.getLogger(__name__)


class ContextRetriever:
    def __init__(
        self,
        embedding_model: EmbeddingModel,
        global_store: GlobalKnowledgeStore,
        memory_store: ConversationMemoryStore,
        *,
        global_limit: int,
        conversation_limit: int,
        score_threshold: float | None,
        max_context_characters: int,
        semantic_routing_policy: SemanticRoutingPolicy | None = None,
    ) -> None:
        self._embedding_model = embedding_model
        self._global_store = global_store
        self._memory_store = memory_store
        self._global_limit = global_limit
        self._conversation_limit = conversation_limit
        self._score_threshold = score_threshold
        self._max_context_characters = max_context_characters
        self._semantic_routing_policy = semantic_routing_policy

    async def retrieve(
        self,
        message: str,
        conversation_id: UUID,
        *,
        allow_direct: bool = True,
    ) -> RetrievedRagContext:
        try:
            embedding = await self._embedding_model.embed_query(message)
        except EmbeddingModelError:
            route = (
                SemanticRoute.DEGRADED
                if self._semantic_routing_policy is not None
                else SemanticRoute.DISABLED
            )
            return RetrievedRagContext(status=RagStatus.DEGRADED, route=route)

        query_vector = embedding.vectors[0].values
        score_threshold = (
            None if self._semantic_routing_policy is not None else self._score_threshold
        )
        global_result, conversation_result = await asyncio.gather(
            self._global_store.search_global(
                GlobalKnowledgeQuery(
                    vector=query_vector,
                    limit=self._global_limit,
                    score_threshold=score_threshold,
                )
            ),
            self._memory_store.search_conversation(
                ConversationMemoryQuery(
                    conversation_id=conversation_id,
                    vector=query_vector,
                    limit=self._conversation_limit,
                    score_threshold=score_threshold,
                )
            ),
            return_exceptions=True,
        )

        degraded = False
        if isinstance(global_result, BaseException):
            if not isinstance(global_result, VectorStoreError):
                raise global_result
            global_matches: tuple[GlobalKnowledgeMatch, ...] = ()
            degraded = True
        else:
            global_matches = global_result

        if isinstance(conversation_result, BaseException):
            if not isinstance(conversation_result, VectorStoreError):
                raise conversation_result
            conversation_matches: tuple[ConversationMemoryMatch, ...] = ()
            degraded = True
        else:
            conversation_matches = conversation_result

        if self._semantic_routing_policy is not None:
            decision = self._semantic_routing_policy.decide(
                global_matches=global_matches,
                conversation_matches=conversation_matches,
                degraded=degraded,
                allow_direct=allow_direct,
            )
            prompt_context = None
            if decision.route in (SemanticRoute.CONTEXTUAL, SemanticRoute.DEGRADED):
                prompt_context = self._build_prompt_context(
                    decision.global_matches,
                    decision.conversation_matches,
                )
            status = {
                SemanticRoute.DIRECT: RagStatus.USED,
                SemanticRoute.CONTEXTUAL: RagStatus.USED,
                SemanticRoute.GENERAL: RagStatus.EMPTY,
                SemanticRoute.DEGRADED: RagStatus.DEGRADED,
            }[decision.route]
            logger.info(
                "semantic_route_selected route=%s top_score=%s global_matches=%s "
                "conversation_matches=%s",
                decision.route.value,
                decision.top_score,
                len(global_matches),
                len(conversation_matches),
            )
            return RetrievedRagContext(
                status=status,
                query_vector=query_vector,
                prompt_context=prompt_context,
                global_matches=len(global_matches),
                conversation_matches=len(conversation_matches),
                route=decision.route,
                top_score=decision.top_score,
                direct_answer=decision.direct_answer,
            )

        prompt_context = self._build_prompt_context(global_matches, conversation_matches)
        if degraded:
            status = RagStatus.DEGRADED
        elif prompt_context is None:
            status = RagStatus.EMPTY
        else:
            status = RagStatus.USED
        return RetrievedRagContext(
            status=status,
            query_vector=query_vector,
            prompt_context=prompt_context,
            global_matches=len(global_matches),
            conversation_matches=len(conversation_matches),
            route=SemanticRoute.DISABLED,
        )

    def _build_prompt_context(
        self,
        global_matches: Sequence[GlobalKnowledgeMatch],
        conversation_matches: Sequence[ConversationMemoryMatch],
    ) -> str | None:
        global_entries = [
            f"[{escape(match.source)} | {escape(match.title)}]\n{escape(match.content)}"
            for match in global_matches
        ]
        conversation_entries = [
            f"User: {escape(match.question)}\nAssistant: {escape(match.answer)}"
            for match in conversation_matches
        ]

        sections: list[str] = []
        remaining = self._max_context_characters
        for tag, entries in (
            ("global_knowledge", global_entries),
            ("conversation_memory", conversation_entries),
        ):
            if not entries:
                continue
            separator = "\n\n" if sections else ""
            section = self._bounded_section(tag, entries, remaining - len(separator))
            if section is None:
                continue
            sections.append(f"{separator}{section}")
            remaining -= len(separator) + len(section)

        return "".join(sections) or None

    @staticmethod
    def _bounded_section(tag: str, entries: Sequence[str], budget: int) -> str | None:
        opening = f"<{tag}>\n"
        closing = f"\n</{tag}>"
        content_budget = budget - len(opening) - len(closing)
        if content_budget <= 0:
            return None

        accepted: list[str] = []
        used = 0
        for entry in entries:
            separator_length = 2 if accepted else 0
            available = content_budget - used - separator_length
            if available <= 0:
                break
            if len(entry) <= available:
                accepted.append(entry)
                used += separator_length + len(entry)
                continue
            if not accepted:
                accepted.append(entry[:available].rstrip())
            break

        if not accepted or not accepted[0]:
            return None
        return f"{opening}{'\n\n'.join(accepted)}{closing}"
