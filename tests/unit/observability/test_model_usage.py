from uuid import UUID

from app.observability.model_usage import observe_model_usage, observe_rag_usage
from app.orchestration.message_processor import MessageResult
from app.orchestration.rag_contracts import RagMessageResult, RagStatus, SemanticRoute
from app.ports.chat_model import ModelProvider
from app.shared.enums import MessageResponseType

ID = UUID("11111111-1111-1111-1111-111111111111")
SENSITIVE_RESPONSE = "DO-NOT-OBSERVE-THIS-RESPONSE"


def message_result(**changes: object) -> MessageResult:
    values: dict[str, object] = {
        "message": SENSITIVE_RESPONSE,
        "conversation_id": ID,
        "correlation_id": ID,
        "response_type": MessageResponseType.AI_GENERATED,
    }
    values.update(changes)
    return MessageResult(**values)  # type: ignore[arg-type]


def test_extracts_only_model_and_rag_aggregate_usage() -> None:
    result = message_result(
        provider=ModelProvider.OPENAI,
        model="gpt-4o-mini",
        input_tokens=12,
        output_tokens=8,
        rag=RagMessageResult(
            status=RagStatus.USED,
            route=SemanticRoute.CONTEXTUAL,
            global_matches=2,
            conversation_matches=3,
            memory_stored=True,
            knowledge_published=False,
        ),
    )

    model = observe_model_usage(result)
    rag = observe_rag_usage(result)

    assert (model.provider, model.model) == ("openai", "gpt-4o-mini")
    assert (model.input_tokens, model.output_tokens, model.tokens_reported) == (12, 8, True)
    assert (rag.status, rag.route) == ("used", "contextual")
    assert (rag.global_matches, rag.conversation_matches) == (2, 3)
    assert (rag.memory_stored, rag.knowledge_published) == (True, False)
    assert SENSITIVE_RESPONSE not in repr(model)
    assert SENSITIVE_RESPONSE not in repr(rag)


def test_missing_model_usage_remains_explicitly_unreported() -> None:
    usage = observe_model_usage(message_result())

    assert usage.provider is None
    assert usage.model is None
    assert usage.input_tokens is None
    assert usage.output_tokens is None
    assert usage.tokens_reported is False


def test_zero_tokens_are_preserved_as_reported_values() -> None:
    usage = observe_model_usage(message_result(input_tokens=0, output_tokens=0))

    assert usage.input_tokens == 0
    assert usage.output_tokens == 0
    assert usage.tokens_reported is True


def test_model_label_is_sanitized_and_bounded() -> None:
    usage = observe_model_usage(message_result(model="bad model\n" + "x" * 150))

    assert usage.model is not None
    assert len(usage.model) <= 100
    assert " " not in usage.model
    assert "\n" not in usage.model
