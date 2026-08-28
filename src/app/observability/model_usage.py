from dataclasses import dataclass

from app.observability.tracing import safe_label
from app.orchestration.message_processor import MessageResult


@dataclass(frozen=True, slots=True)
class ModelUsageObservation:
    provider: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    tokens_reported: bool


@dataclass(frozen=True, slots=True)
class RagUsageObservation:
    status: str
    route: str
    global_matches: int
    conversation_matches: int
    memory_stored: bool
    knowledge_published: bool


def observe_model_usage(result: MessageResult) -> ModelUsageObservation:
    provider = safe_label(result.provider.value) if result.provider is not None else None
    model = safe_label(result.model) if result.model is not None else None
    return ModelUsageObservation(
        provider=provider,
        model=model,
        input_tokens=result.input_tokens,
        output_tokens=result.output_tokens,
        tokens_reported=result.input_tokens is not None or result.output_tokens is not None,
    )


def observe_rag_usage(result: MessageResult) -> RagUsageObservation:
    return RagUsageObservation(
        status=result.rag.status.value,
        route=result.rag.route.value,
        global_matches=result.rag.global_matches,
        conversation_matches=result.rag.conversation_matches,
        memory_stored=result.rag.memory_stored,
        knowledge_published=result.rag.knowledge_published,
    )
