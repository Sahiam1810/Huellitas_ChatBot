from typing import Protocol

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
    def __init__(self, graph: InvokableGraph) -> None:
        self._graph = graph

    async def process(
        self,
        command: MessageCommand,
        context: ExecutionContext,
    ) -> MessageResult:
        state = await self._graph.ainvoke(
            {"command": message_command_to_state(command)},
            config={"configurable": {"thread_id": str(command.conversation_id)}},
            context=context,
        )
        result = state.get("result")
        if result is None:
            raise GraphCompositionError("Graph execution did not produce a final result")
        return message_result_from_state(result)
