from uuid import UUID

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.orchestration.execution_context import ExecutionContext
from app.orchestration.intent_router import RoutingDecision
from app.orchestration.main_graph import build_main_graph
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.module_executor import ModuleExecutionRequest, ModuleResult
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.module_registry import ModuleRegistry
from app.orchestration.state import message_command_to_state, message_result_from_state
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.enums import MessageResponseType
from app.shared.exceptions import GraphCompositionError, InvalidModuleResultError


def command(**overrides: object) -> MessageCommand:
    values = {
        "message": "Quiero ver mis citas",
        "conversation_id": UUID("11111111-1111-1111-1111-111111111111"),
        "user_id": UUID("22222222-2222-2222-2222-222222222222"),
        "pet_id": None,
        "channel": "web",
        "language": "es-CO",
        "roles": ("Cliente",),
        "is_escalated": False,
        "correlation_id": UUID("33333333-3333-3333-3333-333333333333"),
        "idempotency_key": "message-001",
        "publish_as_global_knowledge": False,
    }
    values.update(overrides)
    return MessageCommand(**values)


def context() -> ExecutionContext:
    return ExecutionContext(
        bearer_token="secret-token-that-must-not-leak",
        principal=AuthenticatedPrincipal(
            account_id=UUID("aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"),
            person_id=UUID("22222222-2222-2222-2222-222222222222"),
            role_id=UUID("bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"),
            role="Cliente",
            username="cliente.demo",
            email="cliente@example.test",
            token_id=UUID("cccccccc-cccc-cccc-cccc-cccccccccccc"),
        ),
        execution_id=UUID("dddddddd-dddd-dddd-dddd-dddddddddddd"),
        correlation_id=UUID("33333333-3333-3333-3333-333333333333"),
    )


def manifest() -> ModuleManifest:
    return ModuleManifest(
        module_id="appointments",
        version="1.0.0",
        description="Appointment operations",
        intents=("appointments.list",),
    )


class GeneralProcessor:
    def __init__(self) -> None:
        self.commands: list[MessageCommand] = []

    async def process(self, current: MessageCommand) -> MessageResult:
        self.commands.append(current)
        return MessageResult(
            message=f"general:{current.message}",
            conversation_id=current.conversation_id,
            correlation_id=current.correlation_id,
            response_type=MessageResponseType.AI_GENERATED,
        )


class Router:
    def __init__(self, decision: RoutingDecision) -> None:
        self.decision = decision
        self.calls = 0

    async def route(
        self,
        current: MessageCommand,
        manifests: tuple[ModuleManifest, ...],
    ) -> RoutingDecision:
        self.calls += 1
        assert current.message == "Quiero ver mis citas"
        assert manifests == (manifest(),)
        return self.decision


class Executor:
    def __init__(self, module_id: str = "appointments") -> None:
        self.module_id = module_id
        self.requests: list[ModuleExecutionRequest] = []
        self.contexts: list[ExecutionContext] = []

    async def execute(
        self,
        request: ModuleExecutionRequest,
        execution_context: ExecutionContext,
    ) -> ModuleResult:
        self.requests.append(request)
        self.contexts.append(execution_context)
        return ModuleResult(
            module_id=self.module_id,
            message="Tienes una cita mañana",
            response_type=MessageResponseType.AI_GENERATED,
        )


def config(current: MessageCommand) -> dict[str, dict[str, str]]:
    return {"configurable": {"thread_id": str(current.conversation_id)}}


@pytest.mark.anyio
async def test_empty_registry_follows_the_existing_general_route_without_router() -> None:
    general = GeneralProcessor()
    graph = build_main_graph(
        general_processor=general,
        registry=ModuleRegistry(),
        router=None,
        checkpointer=InMemorySaver(),
    )
    current = command()

    state = await graph.ainvoke(
        {"command": message_command_to_state(current)},
        config=config(current),
        context=context(),
    )

    assert message_result_from_state(state["result"]).message == ("general:Quiero ver mis citas")
    assert state["fallback_reason"] == "module_registry_empty"
    assert general.commands == [current]


@pytest.mark.anyio
async def test_escalated_conversation_ends_before_routing_or_general_processing() -> None:
    general = GeneralProcessor()
    executor = Executor()
    registry = ModuleRegistry()
    registry.register(manifest(), executor)
    router = Router(RoutingDecision.module(intent="appointments.list", module_id="appointments"))
    graph = build_main_graph(general, registry, router, InMemorySaver())
    current = command(is_escalated=True)

    state = await graph.ainvoke(
        {"command": message_command_to_state(current)},
        config=config(current),
        context=context(),
    )

    result = message_result_from_state(state["result"])
    assert result.response_type is MessageResponseType.HUMAN_CONTROLLED
    assert result.message is None
    assert general.commands == []
    assert router.calls == 0
    assert executor.requests == []


@pytest.mark.anyio
async def test_selected_module_receives_only_the_neutral_request_and_runtime_context() -> None:
    general = GeneralProcessor()
    executor = Executor()
    registry = ModuleRegistry()
    selected_manifest = manifest()
    registry.register(selected_manifest, executor)
    router = Router(RoutingDecision.module(intent="appointments.list", module_id="appointments"))
    graph = build_main_graph(general, registry, router, InMemorySaver())
    current = command()
    execution_context = context()

    state = await graph.ainvoke(
        {"command": message_command_to_state(current)},
        config=config(current),
        context=execution_context,
    )

    result = message_result_from_state(state["result"])
    assert result.message == "Tienes una cita mañana"
    assert result.module == "appointments"
    assert state["selected_module_id"] == "appointments"
    assert executor.requests == [
        ModuleExecutionRequest(
            command=current,
            intent="appointments.list",
            manifest=selected_manifest,
        )
    ]
    assert executor.contexts == [execution_context]
    assert general.commands == []


@pytest.mark.anyio
async def test_telegram_guest_never_calls_router_or_module_executor() -> None:
    general = GeneralProcessor()
    executor = Executor()
    registry = ModuleRegistry()
    registry.register(manifest(), executor)
    router = Router(RoutingDecision.module(intent="appointments.list", module_id="appointments"))
    graph = build_main_graph(general, registry, router, InMemorySaver())
    current = command(roles=("TelegramGuest",))

    state = await graph.ainvoke(
        {"command": message_command_to_state(current)},
        config=config(current),
        context=context(),
    )

    assert message_result_from_state(state["result"]).message == "general:Quiero ver mis citas"
    assert state["fallback_reason"] == "guest_general_only"
    assert general.commands == [current]
    assert router.calls == 0
    assert executor.requests == []


@pytest.mark.anyio
@pytest.mark.parametrize(
    "decision",
    [RoutingDecision.unknown("not matched"), RoutingDecision.ambiguous("several matches")],
)
async def test_non_selected_routing_falls_back_to_general_processing(
    decision: RoutingDecision,
) -> None:
    general = GeneralProcessor()
    registry = ModuleRegistry()
    registry.register(manifest(), Executor())
    graph = build_main_graph(general, registry, Router(decision), InMemorySaver())
    current = command()

    state = await graph.ainvoke(
        {"command": message_command_to_state(current)},
        config=config(current),
        context=context(),
    )

    assert message_result_from_state(state["result"]).message == ("general:Quiero ver mis citas")
    assert state["fallback_reason"] == decision.reason
    assert general.commands == [current]


def test_non_empty_registry_requires_a_router_and_every_executor() -> None:
    registry_without_executor = ModuleRegistry()
    registry_without_executor.register(manifest())

    with pytest.raises(GraphCompositionError, match="executor"):
        build_main_graph(
            GeneralProcessor(),
            registry_without_executor,
            Router(RoutingDecision.unknown("not matched")),
            InMemorySaver(),
        )

    registry = ModuleRegistry()
    registry.register(manifest(), Executor())
    with pytest.raises(GraphCompositionError, match="router"):
        build_main_graph(GeneralProcessor(), registry, None, InMemorySaver())


@pytest.mark.anyio
async def test_router_cannot_select_an_unregistered_module() -> None:
    registry = ModuleRegistry()
    registry.register(manifest(), Executor())
    graph = build_main_graph(
        GeneralProcessor(),
        registry,
        Router(RoutingDecision.module(intent="appointments.list", module_id="missing")),
        InMemorySaver(),
    )
    current = command()

    with pytest.raises(GraphCompositionError, match="unregistered") as captured:
        await graph.ainvoke(
            {"command": message_command_to_state(current)},
            config=config(current),
            context=context(),
        )

    assert "secret-token" not in str(captured.value)


@pytest.mark.anyio
async def test_module_cannot_return_a_result_for_another_module() -> None:
    registry = ModuleRegistry()
    registry.register(manifest(), Executor(module_id="services_catalog"))
    graph = build_main_graph(
        GeneralProcessor(),
        registry,
        Router(RoutingDecision.module(intent="appointments.list", module_id="appointments")),
        InMemorySaver(),
    )
    current = command()

    with pytest.raises(InvalidModuleResultError) as captured:
        await graph.ainvoke(
            {"command": message_command_to_state(current)},
            config=config(current),
            context=context(),
        )

    assert "secret-token" not in str(captured.value)


def test_graph_exposes_the_approved_explicit_node_names() -> None:
    graph = build_main_graph(
        GeneralProcessor(), ModuleRegistry(), None, InMemorySaver()
    ).get_graph()

    assert {
        "initialize_run",
        "check_escalation",
        "build_human_controlled",
        "route_intent",
        "execute_general",
        "execute_module",
        "normalize_result",
    }.issubset(graph.nodes)
