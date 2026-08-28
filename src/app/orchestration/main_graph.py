from typing import Protocol

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime

from app.orchestration.execution_context import ExecutionContext
from app.orchestration.intent_router import IntentRouter, RoutingKind
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.module_executor import ModuleExecutionRequest
from app.orchestration.module_registry import ModuleNotFoundError, ModuleRegistry
from app.orchestration.response_builder import (
    build_human_controlled_result,
    normalize_module_result,
)
from app.orchestration.state import MainGraphState, initial_run_update
from app.shared.exceptions import GraphCompositionError


class GeneralMessageProcessor(Protocol):
    async def process(self, command: MessageCommand) -> MessageResult: ...


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
        return initial_run_update(state["command"])

    async def check_escalation(_: MainGraphState) -> MainGraphState:
        return {}

    async def build_human_controlled(state: MainGraphState) -> MainGraphState:
        return {"result": build_human_controlled_result(state["command"])}

    async def route_intent(state: MainGraphState) -> MainGraphState:
        manifests = registry.list_manifests()
        if not manifests:
            return {"fallback_reason": "module_registry_empty"}
        if router is None:
            raise GraphCompositionError("Intent router is not configured")
        decision = await router.route(state["command"], manifests)
        if decision.kind is not RoutingKind.MODULE:
            return {"routing": decision, "fallback_reason": decision.reason}
        if decision.module_id is None or decision.intent is None:
            raise GraphCompositionError("Router returned incomplete module selection")
        try:
            registration = registry.get_registration(decision.module_id)
        except ModuleNotFoundError:
            raise GraphCompositionError("Router selected an unregistered module") from None
        if decision.intent not in registration.manifest.intents:
            raise GraphCompositionError("Router selected an intent outside the module manifest")
        return {
            "routing": decision,
            "selected_module_id": registration.manifest.module_id,
        }

    async def execute_general(state: MainGraphState) -> MainGraphState:
        return {"result": await general_processor.process(state["command"])}

    async def execute_module(
        state: MainGraphState,
        runtime: Runtime[ExecutionContext],
    ) -> MainGraphState:
        decision = state.get("routing")
        selected_module_id = state.get("selected_module_id")
        if (
            decision is None
            or decision.intent is None
            or selected_module_id is None
            or runtime.context is None
        ):
            raise GraphCompositionError("Module execution state is incomplete")
        registration = registry.get_registration(selected_module_id)
        if registration.executor is None:
            raise GraphCompositionError("Selected module executor is not configured")
        result = await registration.executor.execute(
            ModuleExecutionRequest(
                command=state["command"],
                intent=decision.intent,
                manifest=registration.manifest,
            ),
            runtime.context,
        )
        return {"module_result": result}

    async def normalize_result(state: MainGraphState) -> MainGraphState:
        module_result = state.get("module_result")
        selected_module_id = state.get("selected_module_id")
        if module_result is None or selected_module_id is None:
            raise GraphCompositionError("Module result state is incomplete")
        manifest = registry.get(selected_module_id)
        return {
            "result": normalize_module_result(state["command"], manifest, module_result)
        }

    def after_escalation(state: MainGraphState) -> str:
        return "human" if state["command"].is_escalated else "route"

    def after_routing(state: MainGraphState) -> str:
        return "module" if state.get("selected_module_id") is not None else "general"

    builder = StateGraph(MainGraphState, context_schema=ExecutionContext)
    builder.add_node("initialize_run", initialize_run)
    builder.add_node("check_escalation", check_escalation)
    builder.add_node("build_human_controlled", build_human_controlled)
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
        {"general": "execute_general", "module": "execute_module"},
    )
    builder.add_edge("execute_general", END)
    builder.add_edge("execute_module", "normalize_result")
    builder.add_edge("normalize_result", END)
    return builder.compile(checkpointer=checkpointer)
