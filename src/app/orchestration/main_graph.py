from dataclasses import replace
from typing import Protocol

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from app.orchestration.execution_context import ExecutionContext
from app.orchestration.guest_access import GUEST_FALLBACK_REASON, is_guest
from app.orchestration.intent_router import IntentRouter, RoutingDecision, RoutingKind
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.module_executor import ModuleExecutionRequest
from app.orchestration.module_registry import ModuleNotFoundError, ModuleRegistry
from app.orchestration.response_builder import (
    build_guest_link_required_result,
    build_human_controlled_result,
    normalize_module_result,
)
from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.orchestration.state import (
    MainGraphState,
    confirmation_from_state,
    confirmation_to_state,
    initial_run_update,
    message_command_from_state,
    message_result_to_state,
    module_result_from_state,
    module_result_to_state,
    routing_decision_from_state,
    routing_decision_to_state,
)
from app.shared.enums import AccessRequirement, MessageResponseType
from app.shared.exceptions import GraphCompositionError, InvalidModuleResultError

MAX_MODULE_HANDOFFS = 2


class GeneralMessageProcessor(Protocol):
    async def process(self, command: MessageCommand) -> MessageResult: ...


_CONFIRMATION_ONLY_REPLIES = {
    "si",
    "no",
    "confirmo",
    "confirmar",
    "acepto",
    "de acuerdo",
    "adelante",
    "cancelar",
}


def _is_confirmation_only(message: str) -> bool:
    return normalize_for_routing(message) in _CONFIRMATION_ONLY_REPLIES


def build_main_graph(
    general_processor: GeneralMessageProcessor,
    registry: ModuleRegistry,
    router: IntentRouter | None,
    checkpointer: BaseCheckpointSaver,
) -> CompiledStateGraph:
    registrations = registry.list_registrations()
    if registrations and router is None:
        raise GraphCompositionError("A non-empty module registry requires an intent router")
    if any(registration.executor is None for registration in registrations):
        raise GraphCompositionError("Every registered module requires an executor")

    async def initialize_run(state: MainGraphState) -> MainGraphState:
        return initial_run_update(state["command"], state.get("confirmation"))

    async def check_escalation(_: MainGraphState) -> MainGraphState:
        return {}

    async def build_human_controlled(state: MainGraphState) -> MainGraphState:
        command = message_command_from_state(state["command"])
        return {"result": message_result_to_state(build_human_controlled_result(command))}

    async def build_guest_link_required(state: MainGraphState) -> MainGraphState:
        command = message_command_from_state(state["command"])
        return {"result": message_result_to_state(build_guest_link_required_result(command))}

    async def route_intent(state: MainGraphState) -> MainGraphState:
        command = message_command_from_state(state["command"])
        guest = is_guest(command.roles)
        pending = confirmation_from_state(state.get("confirmation"))
        pending_expired = pending is not None and pending.is_expired()
        if pending_expired:
            pending = None
        if pending is not None:
            try:
                registration = registry.get_registration(pending.module_id)
            except ModuleNotFoundError:
                return {"confirmation": None, "fallback_reason": "confirmation_module_missing"}
            if pending.intent not in registration.manifest.intents:
                return {"confirmation": None, "fallback_reason": "confirmation_intent_missing"}
            if guest and not registration.manifest.guest_accessible:
                return {
                    "confirmation": None,
                    "fallback_reason": "guest_link_required",
                    "guest_link_required": True,
                }
            decision = RoutingDecision.module(
                intent=pending.intent,
                module_id=pending.module_id,
            )
            return {
                "routing": routing_decision_to_state(decision),
                "selected_module_id": pending.module_id,
            }
        manifests = registry.list_manifests()
        if not manifests:
            return {
                "fallback_reason": (GUEST_FALLBACK_REASON if guest else "module_registry_empty")
            }
        if router is None:
            raise GraphCompositionError("Intent router is not configured")
        decision = await router.route(command, manifests)
        if decision.kind is not RoutingKind.MODULE:
            if pending_expired and (
                decision.kind is RoutingKind.AMBIGUOUS
                or _is_confirmation_only(command.message)
            ):
                return {
                    "routing": routing_decision_to_state(decision),
                    "confirmation": None,
                    "fallback_reason": "confirmation_expired",
                    "result": message_result_to_state(
                        MessageResult(
                            message=(
                                "El proceso anterior venció. Indícame nuevamente qué deseas "
                                "hacer, por ejemplo registrar una mascota o agendar una cita."
                            ),
                            conversation_id=command.conversation_id,
                            correlation_id=command.correlation_id,
                            response_type=MessageResponseType.RETRIEVED,
                        )
                    ),
                }
            if guest:
                return {
                    "routing": routing_decision_to_state(decision),
                    "fallback_reason": GUEST_FALLBACK_REASON,
                }
            return {
                "routing": routing_decision_to_state(decision),
                "fallback_reason": decision.reason,
                "confirmation": None if pending_expired else state.get("confirmation"),
            }
        if decision.module_id is None or decision.intent is None:
            raise GraphCompositionError("Router returned incomplete module selection")
        try:
            registration = registry.get_registration(decision.module_id)
        except ModuleNotFoundError:
            raise GraphCompositionError("Router selected an unregistered module") from None
        if decision.intent not in registration.manifest.intents:
            raise GraphCompositionError("Router selected an intent outside the module manifest")
        if guest and not registration.manifest.guest_accessible:
            return {
                "routing": routing_decision_to_state(decision),
                "fallback_reason": "guest_link_required",
                "guest_link_required": True,
            }
        return {
            "routing": routing_decision_to_state(decision),
            "selected_module_id": registration.manifest.module_id,
            "confirmation": None if pending_expired else state.get("confirmation"),
        }

    async def execute_general(state: MainGraphState) -> MainGraphState:
        command = message_command_from_state(state["command"])
        return {"result": message_result_to_state(await general_processor.process(command))}

    async def execute_module(
        state: MainGraphState,
        runtime: Runtime[ExecutionContext],
    ) -> MainGraphState:
        routing_state = state.get("routing")
        selected_module_id = state.get("selected_module_id")
        if routing_state is None or selected_module_id is None or runtime.context is None:
            raise GraphCompositionError("Module execution state is incomplete")
        decision = routing_decision_from_state(routing_state)
        if decision.intent is None:
            raise GraphCompositionError("Module execution routing is incomplete")
        command = message_command_from_state(state["command"])
        registration = registry.get_registration(selected_module_id)
        if registration.executor is None:
            raise GraphCompositionError("Selected module executor is not configured")
        request = ModuleExecutionRequest(
            command=command,
            intent=decision.intent,
            manifest=registration.manifest,
            pending_confirmation=confirmation_from_state(state.get("confirmation")),
        )
        messages: list[str] = []
        handoff_count = 0
        while True:
            result = await registration.executor.execute(request, runtime.context)
            if result.module_id.strip() != registration.manifest.module_id:
                raise InvalidModuleResultError("module result does not match the selected module")
            if result.message:
                messages.append(result.message)
            handoff = result.handoff
            if handoff is None:
                break
            if handoff_count >= MAX_MODULE_HANDOFFS:
                raise GraphCompositionError("Module handoff limit exceeded")
            target = handoff.target
            if target.module_id == registration.manifest.module_id:
                raise GraphCompositionError("Module handoff cycle detected")
            try:
                next_registration = registry.get_registration(target.module_id)
            except ModuleNotFoundError:
                raise GraphCompositionError("Module handoff target is not registered") from None
            if target.intent not in next_registration.manifest.intents:
                raise GraphCompositionError("Module handoff intent is outside the target manifest")
            if next_registration.executor is None:
                raise GraphCompositionError("Module handoff target executor is not configured")
            if is_guest(command.roles) and not next_registration.manifest.guest_accessible:
                result = replace(
                    result,
                    access_requirement=AccessRequirement.IDENTITY_VERIFICATION,
                    handoff=None,
                )
                break
            registration = next_registration
            selected_module_id = registration.manifest.module_id
            request = ModuleExecutionRequest(
                command=command,
                intent=target.intent,
                manifest=registration.manifest,
                continuation=handoff.continuation,
            )
            handoff_count += 1
        result = replace(result, message="\n\n".join(messages), handoff=None)
        return {
            "module_result": module_result_to_state(result),
            "confirmation": confirmation_to_state(result.pending_confirmation),
            "selected_module_id": selected_module_id,
        }

    async def normalize_result(state: MainGraphState) -> MainGraphState:
        module_result_state = state.get("module_result")
        selected_module_id = state.get("selected_module_id")
        if module_result_state is None or selected_module_id is None:
            raise GraphCompositionError("Module result state is incomplete")
        manifest = registry.get(selected_module_id)
        return {
            "result": message_result_to_state(
                normalize_module_result(
                    message_command_from_state(state["command"]),
                    manifest,
                    module_result_from_state(module_result_state),
                )
            )
        }

    def after_escalation(state: MainGraphState) -> str:
        return "human" if state["command"]["is_escalated"] else "route"

    def after_routing(state: MainGraphState) -> str:
        if state.get("result") is not None:
            return "completed"
        if state.get("guest_link_required"):
            return "guest_link_required"
        return "module" if state.get("selected_module_id") is not None else "general"

    builder = StateGraph(MainGraphState, context_schema=ExecutionContext)
    builder.add_node("initialize_run", initialize_run)
    builder.add_node("check_escalation", check_escalation)
    builder.add_node("build_human_controlled", build_human_controlled)
    builder.add_node("build_guest_link_required", build_guest_link_required)
    builder.add_node("route_intent", route_intent)
    builder.add_node("execute_general", execute_general)
    builder.add_node("execute_module", execute_module)
    builder.add_node("normalize_result", normalize_result)
    builder.add_edge(START, "initialize_run")
    builder.add_edge("initialize_run", "check_escalation")
    builder.add_conditional_edges(
        "check_escalation",
        after_escalation,
        {"human": "build_human_controlled", "route": "route_intent"},
    )
    builder.add_edge("build_human_controlled", END)
    builder.add_conditional_edges(
        "route_intent",
        after_routing,
        {
            "general": "execute_general",
            "module": "execute_module",
            "guest_link_required": "build_guest_link_required",
            "completed": END,
        },
    )
    builder.add_edge("build_guest_link_required", END)
    builder.add_edge("execute_general", END)
    builder.add_edge("execute_module", "normalize_result")
    builder.add_edge("normalize_result", END)
    return builder.compile(checkpointer=checkpointer)
