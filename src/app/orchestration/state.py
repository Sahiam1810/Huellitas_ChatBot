from typing import TypedDict
from uuid import UUID

from app.orchestration.intent_router import RoutingDecision, RoutingKind
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.module_executor import ModuleResult
from app.orchestration.rag_contracts import RagMessageResult, RagStatus, SemanticRoute
from app.ports.chat_model import ModelProvider
from app.shared.enums import MessageResponseType


class MessageCommandState(TypedDict):
    message: str
    conversation_id: str
    user_id: str
    pet_id: str | None
    channel: str
    language: str
    roles: list[str]
    is_escalated: bool
    correlation_id: str
    idempotency_key: str
    publish_as_global_knowledge: bool


class RagMessageResultState(TypedDict):
    status: str
    global_matches: int
    conversation_matches: int
    memory_stored: bool
    knowledge_published: bool
    route: str
    top_score: float | None


class MessageResultState(TypedDict):
    message: str | None
    conversation_id: str
    correlation_id: str
    response_type: str
    provider: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    module: str | None
    rag: RagMessageResultState
    idempotency_replayed: bool


class RoutingDecisionState(TypedDict):
    kind: str
    intent: str | None
    module_id: str | None
    reason: str | None


class ModuleResultState(TypedDict):
    module_id: str
    message: str | None
    response_type: str
    provider: str | None
    model: str | None
    input_tokens: int | None
    output_tokens: int | None
    rag: RagMessageResultState


class MainGraphState(TypedDict, total=False):
    command: MessageCommandState
    routing: RoutingDecisionState | None
    selected_module_id: str | None
    module_result: ModuleResultState | None
    result: MessageResultState | None
    fallback_reason: str | None
    safe_error: str | None
    confirmation: dict[str, object] | None
    schema_version: int


def message_command_to_state(command: MessageCommand) -> MessageCommandState:
    return {
        "message": command.message,
        "conversation_id": str(command.conversation_id),
        "user_id": str(command.user_id),
        "pet_id": str(command.pet_id) if command.pet_id is not None else None,
        "channel": command.channel,
        "language": command.language,
        "roles": list(command.roles),
        "is_escalated": command.is_escalated,
        "correlation_id": str(command.correlation_id),
        "idempotency_key": command.idempotency_key,
        "publish_as_global_knowledge": command.publish_as_global_knowledge,
    }


def message_command_from_state(state: MessageCommandState) -> MessageCommand:
    return MessageCommand(
        message=state["message"],
        conversation_id=UUID(state["conversation_id"]),
        user_id=UUID(state["user_id"]),
        pet_id=UUID(state["pet_id"]) if state["pet_id"] is not None else None,
        channel=state["channel"],
        language=state["language"],
        roles=tuple(state["roles"]),
        is_escalated=state["is_escalated"],
        correlation_id=UUID(state["correlation_id"]),
        idempotency_key=state["idempotency_key"],
        publish_as_global_knowledge=state["publish_as_global_knowledge"],
    )


def rag_result_to_state(result: RagMessageResult) -> RagMessageResultState:
    return {
        "status": result.status.value,
        "global_matches": result.global_matches,
        "conversation_matches": result.conversation_matches,
        "memory_stored": result.memory_stored,
        "knowledge_published": result.knowledge_published,
        "route": result.route.value,
        "top_score": result.top_score,
    }


def rag_result_from_state(state: RagMessageResultState) -> RagMessageResult:
    return RagMessageResult(
        status=RagStatus(state["status"]),
        global_matches=state["global_matches"],
        conversation_matches=state["conversation_matches"],
        memory_stored=state["memory_stored"],
        knowledge_published=state["knowledge_published"],
        route=SemanticRoute(state["route"]),
        top_score=state["top_score"],
    )


def message_result_to_state(result: MessageResult) -> MessageResultState:
    return {
        "message": result.message,
        "conversation_id": str(result.conversation_id),
        "correlation_id": str(result.correlation_id),
        "response_type": result.response_type.value,
        "provider": result.provider.value if result.provider is not None else None,
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "module": result.module,
        "rag": rag_result_to_state(result.rag),
        "idempotency_replayed": result.idempotency_replayed,
    }


def message_result_from_state(state: MessageResultState) -> MessageResult:
    provider = state["provider"]
    return MessageResult(
        message=state["message"],
        conversation_id=UUID(state["conversation_id"]),
        correlation_id=UUID(state["correlation_id"]),
        response_type=MessageResponseType(state["response_type"]),
        provider=ModelProvider(provider) if provider is not None else None,
        model=state["model"],
        input_tokens=state["input_tokens"],
        output_tokens=state["output_tokens"],
        module=state["module"],
        rag=rag_result_from_state(state["rag"]),
        idempotency_replayed=state["idempotency_replayed"],
    )


def routing_decision_to_state(decision: RoutingDecision) -> RoutingDecisionState:
    return {
        "kind": decision.kind.value,
        "intent": decision.intent,
        "module_id": decision.module_id,
        "reason": decision.reason,
    }


def routing_decision_from_state(state: RoutingDecisionState) -> RoutingDecision:
    return RoutingDecision(
        kind=RoutingKind(state["kind"]),
        intent=state["intent"],
        module_id=state["module_id"],
        reason=state["reason"],
    )


def module_result_to_state(result: ModuleResult) -> ModuleResultState:
    return {
        "module_id": result.module_id,
        "message": result.message,
        "response_type": result.response_type.value,
        "provider": result.provider.value if result.provider is not None else None,
        "model": result.model,
        "input_tokens": result.input_tokens,
        "output_tokens": result.output_tokens,
        "rag": rag_result_to_state(result.rag),
    }


def module_result_from_state(state: ModuleResultState) -> ModuleResult:
    provider = state["provider"]
    return ModuleResult(
        module_id=state["module_id"],
        message=state["message"],
        response_type=MessageResponseType(state["response_type"]),
        provider=ModelProvider(provider) if provider is not None else None,
        model=state["model"],
        input_tokens=state["input_tokens"],
        output_tokens=state["output_tokens"],
        rag=rag_result_from_state(state["rag"]),
    )


def initial_run_update(command: MessageCommandState) -> MainGraphState:
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
