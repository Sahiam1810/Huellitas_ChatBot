from collections.abc import Callable
from contextlib import suppress
from time import perf_counter
from typing import Protocol

from app.observability.model_usage import observe_model_usage, observe_rag_usage
from app.observability.tracing import (
    GraphRunCompleted,
    GraphRunFailed,
    GraphRunObserver,
    GraphRunStarted,
    NullGraphRunObserver,
    classify_failure,
    classify_fallback,
    classify_route,
    safe_label,
)
from app.orchestration.execution_context import ExecutionContext
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.state import (
    MainGraphState,
    message_command_to_state,
    message_result_from_state,
)
from app.shared.exceptions import GraphCompositionError


class InvokableGraph(Protocol):
    async def ainvoke(
        self,
        input: MainGraphState,
        *,
        config: dict[str, dict[str, str]],
        context: ExecutionContext,
    ) -> MainGraphState: ...


class LangGraphMessageHandler:
    def __init__(
        self,
        graph: InvokableGraph,
        *,
        observer: GraphRunObserver | None = None,
        clock: Callable[[], float] = perf_counter,
    ) -> None:
        self._graph = graph
        self._observer = observer or NullGraphRunObserver()
        self._clock = clock

    async def process(
        self,
        command: MessageCommand,
        context: ExecutionContext,
    ) -> MessageResult:
        started_at = self._clock()
        self._notify(
            "started",
            GraphRunStarted(context.correlation_id, context.execution_id),
        )
        try:
            state = await self._graph.ainvoke(
                {"command": message_command_to_state(command)},
                config={"configurable": {"thread_id": str(command.conversation_id)}},
                context=context,
            )
            result_state = state.get("result")
            if result_state is None:
                raise GraphCompositionError("Graph execution did not produce a final result")
            result = message_result_from_state(result_state)
            duration_ms = (self._clock() - started_at) * 1000
            model = observe_model_usage(result)
            rag = observe_rag_usage(result)
            completed = GraphRunCompleted(
                correlation_id=context.correlation_id,
                execution_id=context.execution_id,
                duration_ms=duration_ms,
                route=classify_route(result),
                fallback=classify_fallback(state),
                module=safe_label(result.module) if result.module is not None else None,
                provider=model.provider,
                model=model.model,
                input_tokens=model.input_tokens,
                output_tokens=model.output_tokens,
                tokens_reported=model.tokens_reported,
                rag_status=rag.status,
                rag_route=rag.route,
                global_matches=rag.global_matches,
                conversation_matches=rag.conversation_matches,
                memory_stored=rag.memory_stored,
                knowledge_published=rag.knowledge_published,
            )
        except Exception as error:
            failed = GraphRunFailed(
                correlation_id=context.correlation_id,
                execution_id=context.execution_id,
                duration_ms=(self._clock() - started_at) * 1000,
                category=classify_failure(error),
            )
            self._notify("failed", failed)
            raise
        self._notify("completed", completed)
        return result

    def _notify(self, method: str, event: object) -> None:
        with suppress(Exception):
            getattr(self._observer, method)(event)
