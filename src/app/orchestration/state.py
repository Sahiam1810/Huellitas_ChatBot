from typing import TypedDict

from app.orchestration.intent_router import RoutingDecision
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.module_executor import ModuleResult


class MainGraphState(TypedDict, total=False):
    command: MessageCommand
    routing: RoutingDecision | None
    selected_module_id: str | None
    module_result: ModuleResult | None
    result: MessageResult | None
    fallback_reason: str | None
    safe_error: str | None
    confirmation: dict[str, object] | None
    schema_version: int


def initial_run_update(command: MessageCommand) -> MainGraphState:
    return {
        "command": command,
        "routing": None,
        "selected_module_id": None,
        "module_result": None,
        "result": None,
        "fallback_reason": None,
        "safe_error": None,
        "confirmation": None,
        "schema_version": 1,
    }
