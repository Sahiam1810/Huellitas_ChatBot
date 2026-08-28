from uuid import UUID

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.orchestration.execution_context import ExecutionContext
from app.orchestration.langgraph_message_handler import LangGraphMessageHandler
from app.orchestration.main_graph import build_main_graph
from app.orchestration.message_handler import MessageHandler
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.module_registry import ModuleRegistry
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.enums import MessageResponseType
from app.shared.exceptions import GraphCompositionError

CONVERSATION_ID = UUID("11111111-1111-1111-1111-111111111111")
OTHER_CONVERSATION_ID = UUID("99999999-9999-9999-9999-999999999999")
CORRELATION_ID = UUID("33333333-3333-3333-3333-333333333333")


def command(
    message: str = "primer mensaje",
    *,
    conversation_id: UUID = CONVERSATION_ID,
    correlation_id: UUID = CORRELATION_ID,
) -> MessageCommand:
    return MessageCommand(
        message=message,
        conversation_id=conversation_id,
        user_id=UUID("22222222-2222-2222-2222-222222222222"),
        pet_id=None,
        channel="web",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=False,
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


class IncompleteGraph:
    async def ainvoke(self, *args: object, **kwargs: object) -> dict[str, object]:
        return {"result": None}


def graph_with_memory() -> object:
    return build_main_graph(
        GeneralProcessor(),
        ModuleRegistry(),
        None,
        InMemorySaver(),
    )


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
