import logging
from uuid import UUID

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.observability.logging import SafeLoggingGraphObserver
from app.observability.tracing import (
    FallbackCategory,
    GraphFailureCategory,
    GraphRoute,
    GraphRunCompleted,
    GraphRunFailed,
    GraphRunStarted,
)
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.intent_router import RoutingDecision
from app.orchestration.langgraph_message_handler import LangGraphMessageHandler
from app.orchestration.main_graph import build_main_graph
from app.orchestration.message_handler import MessageHandler
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.module_executor import ModuleExecutionRequest, ModuleResult
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.module_registry import ModuleRegistry
from app.orchestration.rag_contracts import RagMessageResult, RagStatus, SemanticRoute
from app.ports.chat_model import ModelProvider
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.enums import MessageResponseType
from app.shared.exceptions import GraphCompositionError, ModelTimeoutError

CONVERSATION_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_CONVERSATION_ID = UUID("99999999-9999-9999-9999-999999999999")
CORRELATION_ID = UUID("33333333-3333-3333-3333-333333333333")


def command(
    message: str = "primer mensaje",
    *,
    conversation_id: UUID = CONVERSATION_ID,
    correlation_id: UUID = CORRELATION_ID,
    is_escalated: bool = False,
) -> MessageCommand:
    return MessageCommand(
        message=message,
        conversation_id=conversation_id,
        user_id=UUID("22222222-2222-2222-2222-222222222222"),
        pet_id=None,
        channel="web",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=is_escalated,
        correlation_id=correlation_id,
        idempotency_key=f"key-{message}",
    )


def context(correlation_id: UUID) -> ExecutionContext:
    return ExecutionContext(
        bearer_token="header.sensitive-payload.signature",
        principal=AuthenticatedPrincipal(
            account_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            person_id=UUID("22222222-2222-2222-2222-222222222222"),
            role_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            role="Cliente",
            username="sensitive.username",
            email="sensitive@example.test",
            token_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        ),
        execution_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        correlation_id=correlation_id,
    )


class GeneralProcessor:
    async def process(self, current: MessageCommand) -> MessageResult:
        return MessageResult(
            message=f"general:{current.message}",
            conversation_id=current.conversation_id,
            correlation_id=current.correlation_id,
            response_type=MessageResponseType.AI_GENERATED,
        )


class ModuleRouter:
    async def route(
        self, current: MessageCommand, manifests: tuple[ModuleManifest, ...]
    ) -> RoutingDecision:
        return RoutingDecision.module(intent="appointments.list", module_id="appointments")


class AppointmentsExecutor:
    async def execute(
        self, request: ModuleExecutionRequest, execution_context: ExecutionContext
    ) -> ModuleResult:
        return ModuleResult(
            module_id="appointments",
            message="SENSITIVE MODULE RESPONSE",
            response_type=MessageResponseType.AI_GENERATED,
            provider=ModelProvider.OPENAI,
            model="gpt-4o-mini",
            input_tokens=9,
            output_tokens=4,
            rag=RagMessageResult(
                status=RagStatus.USED,
                route=SemanticRoute.CONTEXTUAL,
                global_matches=2,
                conversation_matches=1,
                memory_stored=True,
            ),
        )


class IncompleteGraph:
    async def ainvoke(self, *args: object, **kwargs: object) -> dict[str, object]:
        return {"result": None}


class FailingGraph:
    def __init__(self, error: Exception) -> None:
        self.error = error

    async def ainvoke(self, *args: object, **kwargs: object) -> dict[str, object]:
        raise self.error


class RecordingObserver:
    def __init__(self, fail_on: str | None = None) -> None:
        self.fail_on = fail_on
        self.started_events: list[GraphRunStarted] = []
        self.completed_events: list[GraphRunCompleted] = []
        self.failed_events: list[GraphRunFailed] = []

    def started(self, event: GraphRunStarted) -> None:
        if self.fail_on == "started":
            raise RuntimeError("observer secret")
        self.started_events.append(event)

    def completed(self, event: GraphRunCompleted) -> None:
        if self.fail_on == "completed":
            raise RuntimeError("observer secret")
        self.completed_events.append(event)

    def failed(self, event: GraphRunFailed) -> None:
        if self.fail_on == "failed":
            raise RuntimeError("observer secret")
        self.failed_events.append(event)


def clock(*values: float) -> object:
    iterator = iter(values)
    return lambda: next(iterator)


def graph_with_memory() -> object:
    return build_main_graph(
        GeneralProcessor(),
        ModuleRegistry(),
        None,
        InMemorySaver(),
    )


def graph_with_module() -> object:
    registry = ModuleRegistry()
    registry.register(
        ModuleManifest(
            module_id="appointments",
            version="1.0.0",
            description="Appointment operations",
            intents=("appointments.list",),
        ),
        AppointmentsExecutor(),
    )
    return build_main_graph(GeneralProcessor(), registry, ModuleRouter(), InMemorySaver())


def graph_config(conversation_id: UUID) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": str(conversation_id)}}


@pytest.mark.anyio
async def test_handler_returns_the_graph_result_using_conversation_as_thread() -> None:
    graph = graph_with_memory()
    handler = LangGraphMessageHandler(graph)
    current = command()

    result = await handler.process(current, context(current.correlation_id))
    snapshot = await graph.aget_state(graph_config(CONVERSATION_ID))

    assert isinstance(handler, MessageHandler)
    assert result.message == "general:primer mensaje"
    assert snapshot.values["command"] == {
        "message": "primer mensaje",
        "conversation_id": str(CONVERSATION_ID),
        "user_id": "22222222-2222-2222-2222-222222222222",
        "pet_id": None,
        "channel": "web",
        "language": "es-CO",
        "roles": ["Cliente"],
        "is_escalated": False,
        "correlation_id": str(CORRELATION_ID),
        "idempotency_key": "key-primer mensaje",
        "publish_as_global_knowledge": False,
    }
    assert snapshot.values["result"]["message"] == "general:primer mensaje"


@pytest.mark.anyio
async def test_reusing_a_thread_clears_transient_values_from_the_previous_run() -> None:
    graph = graph_with_memory()
    handler = LangGraphMessageHandler(graph)
    first = command()
    second = command(
        "segundo mensaje",
        correlation_id=UUID("44444444-4444-4444-4444-444444444444"),
    )

    await handler.process(first, context(first.correlation_id))
    second_result = await handler.process(second, context(second.correlation_id))
    snapshot = await graph.aget_state(graph_config(CONVERSATION_ID))

    assert second_result.message == "general:segundo mensaje"
    assert second_result.correlation_id == second.correlation_id
    assert snapshot.values["command"]["message"] == "segundo mensaje"
    assert snapshot.values["command"]["roles"] == ["Cliente"]
    assert snapshot.values["routing"] is None
    assert snapshot.values["module_result"] is None
    assert snapshot.values["safe_error"] is None


@pytest.mark.anyio
async def test_different_conversations_keep_independent_checkpoints() -> None:
    graph = graph_with_memory()
    handler = LangGraphMessageHandler(graph)
    first = command("conversation one")
    second = command("conversation two", conversation_id=OTHER_CONVERSATION_ID)

    await handler.process(first, context(first.correlation_id))
    await handler.process(second, context(second.correlation_id))
    first_snapshot = await graph.aget_state(graph_config(CONVERSATION_ID))
    second_snapshot = await graph.aget_state(graph_config(OTHER_CONVERSATION_ID))

    assert first_snapshot.values["command"]["message"] == "conversation one"
    assert second_snapshot.values["command"]["message"] == "conversation two"


@pytest.mark.anyio
async def test_checkpoint_state_excludes_token_and_authenticated_context() -> None:
    graph = graph_with_memory()
    handler = LangGraphMessageHandler(graph)
    current = command()

    await handler.process(current, context(current.correlation_id))
    snapshot = await graph.aget_state(graph_config(CONVERSATION_ID))
    serialized_state = repr(snapshot.values)

    assert "header.sensitive-payload.signature" not in serialized_state
    assert "sensitive.username" not in serialized_state
    assert "sensitive@example.test" not in serialized_state
    assert "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa" not in serialized_state
    assert "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb" not in serialized_state
    assert "cccccccc-cccc-cccc-cccc-cccccccccccc" not in serialized_state
    assert "dddddddd-dddd-dddd-dddd-dddddddddddd" not in serialized_state
    assert "ExecutionContext" not in serialized_state


@pytest.mark.anyio
async def test_handler_rejects_a_graph_without_a_final_result() -> None:
    current = command()

    with pytest.raises(GraphCompositionError, match="final result"):
        await LangGraphMessageHandler(IncompleteGraph()).process(
            current,
            context(current.correlation_id),
        )


@pytest.mark.anyio
async def test_handler_observes_one_complete_general_graph_execution() -> None:
    observer = RecordingObserver()
    current = command()
    execution_context = context(current.correlation_id)
    handler = LangGraphMessageHandler(
        graph_with_memory(),
        observer=observer,
        clock=clock(10.0, 10.125),  # type: ignore[arg-type]
    )

    result = await handler.process(current, execution_context)

    assert result.message == "general:primer mensaje"
    assert observer.started_events == [
        GraphRunStarted(current.correlation_id, execution_context.execution_id)
    ]
    completed = observer.completed_events[0]
    assert completed.duration_ms == pytest.approx(125.0)
    assert completed.route is GraphRoute.GENERAL
    assert completed.fallback is FallbackCategory.MODULE_REGISTRY_EMPTY
    assert completed.rag_status == "disabled"
    assert completed.tokens_reported is False
    assert observer.failed_events == []


@pytest.mark.anyio
async def test_handler_observes_human_controlled_route_without_model_usage() -> None:
    observer = RecordingObserver()
    current = command(is_escalated=True)
    execution_context = context(current.correlation_id)

    await LangGraphMessageHandler(
        graph_with_memory(),
        observer=observer,
        clock=clock(2.0, 2.010),  # type: ignore[arg-type]
    ).process(current, execution_context)

    event = observer.completed_events[0]
    assert (event.correlation_id, event.execution_id) == (
        current.correlation_id,
        execution_context.execution_id,
    )
    assert event.duration_ms == pytest.approx(10.0)
    assert event.route is GraphRoute.HUMAN_CONTROLLED
    assert event.fallback is FallbackCategory.NONE
    assert event.module is None
    assert event.provider is event.model is None
    assert event.input_tokens is event.output_tokens is None
    assert event.tokens_reported is False
    assert (event.rag_status, event.rag_route) == ("skipped", "skipped")
    assert (event.global_matches, event.conversation_matches) == (0, 0)
    assert (event.memory_stored, event.knowledge_published) == (False, False)
    assert observer.failed_events == []


@pytest.mark.anyio
async def test_handler_observes_complete_module_usage() -> None:
    observer = RecordingObserver()
    current = command()
    execution_context = context(current.correlation_id)

    await LangGraphMessageHandler(
        graph_with_module(),
        observer=observer,
        clock=clock(4.0, 4.050),  # type: ignore[arg-type]
    ).process(current, execution_context)

    event = observer.completed_events[0]
    assert (event.correlation_id, event.execution_id) == (
        current.correlation_id,
        execution_context.execution_id,
    )
    assert event.duration_ms == pytest.approx(50.0)
    assert event.route is GraphRoute.MODULE
    assert event.fallback is FallbackCategory.NONE
    assert event.module == "appointments"
    assert (event.provider, event.model) == ("openai", "gpt-4o-mini")
    assert (event.input_tokens, event.output_tokens) == (9, 4)
    assert (event.rag_status, event.rag_route) == ("used", "contextual")
    assert (event.global_matches, event.conversation_matches) == (2, 1)
    assert event.memory_stored is True
    assert event.knowledge_published is False
    assert event.tokens_reported is True
    assert observer.failed_events == []


@pytest.mark.anyio
async def test_handler_and_logging_observer_never_log_conversational_data(caplog: object) -> None:
    logger = logging.getLogger("test.graph.handler.privacy")
    current = command(message="SENSITIVE USER MESSAGE")
    with caplog.at_level(logging.INFO, logger=logger.name):  # type: ignore[attr-defined]
        await LangGraphMessageHandler(
            graph_with_module(),
            observer=SafeLoggingGraphObserver(logger),
            clock=clock(5.0, 5.010),  # type: ignore[arg-type]
        ).process(current, context(current.correlation_id))

    output = caplog.text  # type: ignore[attr-defined]
    for forbidden in (
        "SENSITIVE USER MESSAGE",
        "SENSITIVE MODULE RESPONSE",
        str(current.conversation_id),
        str(current.user_id),
        "header.sensitive-payload.signature",
        "sensitive.username",
        "sensitive@example.test",
    ):
        assert forbidden not in output


@pytest.mark.anyio
async def test_handler_preserves_original_failure_and_reports_safe_category() -> None:
    error = ModelTimeoutError("SENSITIVE EXCEPTION TEXT")
    observer = RecordingObserver()
    current = command()
    handler = LangGraphMessageHandler(
        FailingGraph(error),
        observer=observer,
        clock=clock(3.0, 3.030),  # type: ignore[arg-type]
    )

    with pytest.raises(ModelTimeoutError) as captured:
        await handler.process(current, context(current.correlation_id))

    assert captured.value is error
    assert observer.failed_events[0].category is GraphFailureCategory.MODEL_TIMEOUT
    assert observer.failed_events[0].duration_ms == pytest.approx(30.0)
    assert "SENSITIVE EXCEPTION TEXT" not in repr(observer.failed_events[0])


@pytest.mark.anyio
@pytest.mark.parametrize("fail_on", ["started", "completed"])
async def test_observer_failure_never_changes_a_successful_result(fail_on: str) -> None:
    current = command()
    result = await LangGraphMessageHandler(
        graph_with_memory(),
        observer=RecordingObserver(fail_on),
        clock=clock(1.0, 1.001),  # type: ignore[arg-type]
    ).process(current, context(current.correlation_id))

    assert result.message == "general:primer mensaje"


@pytest.mark.anyio
async def test_failed_observer_never_replaces_original_graph_error() -> None:
    original = ModelTimeoutError("original")
    current = command()
    handler = LangGraphMessageHandler(
        FailingGraph(original),
        observer=RecordingObserver("failed"),
        clock=clock(1.0, 1.001),  # type: ignore[arg-type]
    )

    with pytest.raises(ModelTimeoutError) as captured:
        await handler.process(current, context(current.correlation_id))

    assert captured.value is original
