from uuid import UUID

import pytest
from langgraph.checkpoint.memory import InMemorySaver

from app.orchestration.execution_context import ExecutionContext
from app.orchestration.intent_router import RoutingDecision
from app.orchestration.main_graph import build_main_graph
from app.orchestration.message_processor import MessageCommand, MessageResult
from app.orchestration.module_executor import (
    ModuleContinuation,
    ModuleExecutionRequest,
    ModuleHandoff,
    ModuleResult,
    PendingConfirmation,
)
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.module_registry import ModuleRegistry
from app.orchestration.state import (
    confirmation_to_state,
    message_command_to_state,
    message_result_from_state,
)
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.enums import AccessRequirement, MessageResponseType
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
        intents=("appointments.list", "appointments.confirmation"),
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


class PublicModuleRouter:
    def __init__(self, selected_manifest: ModuleManifest) -> None:
        self.selected_manifest = selected_manifest
        self.calls = 0

    async def route(
        self,
        current: MessageCommand,
        manifests: tuple[ModuleManifest, ...],
    ) -> RoutingDecision:
        self.calls += 1
        assert manifests == (self.selected_manifest,)
        return RoutingDecision.module(
            intent=self.selected_manifest.intents[0],
            module_id=self.selected_manifest.module_id,
        )


class FixedRouter:
    def __init__(self, decision: RoutingDecision) -> None:
        self.decision = decision

    async def route(
        self,
        current: MessageCommand,
        manifests: tuple[ModuleManifest, ...],
    ) -> RoutingDecision:
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


class ConfirmingExecutor(Executor):
    async def execute(
        self,
        request: ModuleExecutionRequest,
        execution_context: ExecutionContext,
    ) -> ModuleResult:
        self.requests.append(request)
        self.contexts.append(execution_context)
        if request.pending_confirmation is None:
            return ModuleResult(
                module_id="appointments",
                message="¿Confirmas?",
                response_type=MessageResponseType.RETRIEVED,
                pending_confirmation=PendingConfirmation.create(
                    module_id="appointments",
                    action="appointments.cancel",
                    payload={"appointment_id": "a-1"},
                    ttl_seconds=600,
                ),
            )
        return ModuleResult(
            module_id="appointments",
            message="Confirmado",
            response_type=MessageResponseType.RETRIEVED,
        )


class ExpiredPetRegistrationExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(module_id="pet_profile")

    async def execute(
        self,
        request: ModuleExecutionRequest,
        execution_context: ExecutionContext,
    ) -> ModuleResult:
        self.requests.append(request)
        self.contexts.append(execution_context)
        if request.pending_confirmation is None:
            return ModuleResult(
                module_id="pet_profile",
                message="¿Cómo se llama tu mascota?",
                response_type=MessageResponseType.RETRIEVED,
                pending_confirmation=PendingConfirmation.create(
                    module_id="pet_profile",
                    action="pets.register.collect",
                    payload={"step": "name"},
                    ttl_seconds=-1,
                    intent="pet_profile.registration",
                ),
            )
        return ModuleResult(
            module_id="pet_profile",
            message="El registro venció.",
            response_type=MessageResponseType.RETRIEVED,
        )


class MessageRouter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def route(
        self,
        current: MessageCommand,
        manifests: tuple[ModuleManifest, ...],
    ) -> RoutingDecision:
        self.calls.append(current.message)
        if current.message == "Registrar una mascota":
            return RoutingDecision.module(
                intent="pets.register",
                module_id="pet_profile",
            )
        if current.message == "Quiero agendar una cita":
            return RoutingDecision.module(
                intent="appointments.list",
                module_id="appointments",
            )
        return RoutingDecision.unknown("not matched")


class HandoffExecutor(Executor):
    def __init__(self, handoff: ModuleHandoff, module_id: str = "appointments") -> None:
        super().__init__(module_id=module_id)
        self.handoff = handoff

    async def execute(
        self,
        request: ModuleExecutionRequest,
        execution_context: ExecutionContext,
    ) -> ModuleResult:
        self.requests.append(request)
        self.contexts.append(execution_context)
        return ModuleResult(
            module_id=self.module_id,
            message="Primero registraré tu mascota.",
            response_type=MessageResponseType.RETRIEVED,
            handoff=self.handoff,
        )


class GuestAppointmentOfferExecutor(Executor):
    def __init__(self) -> None:
        super().__init__(module_id="veterinary_guidance")

    async def execute(
        self,
        request: ModuleExecutionRequest,
        execution_context: ExecutionContext,
    ) -> ModuleResult:
        self.requests.append(request)
        self.contexts.append(execution_context)
        if request.pending_confirmation is None:
            return ModuleResult(
                module_id=self.module_id,
                message="Puedo ayudarte a agendar una cita.",
                response_type=MessageResponseType.RETRIEVED,
                pending_confirmation=PendingConfirmation.create(
                    module_id=self.module_id,
                    action="guidance.offer_appointment",
                    payload={},
                    ttl_seconds=600,
                    intent="guidance.appointment_offer",
                ),
            )
        return ModuleResult(
            module_id=self.module_id,
            message="Primero verificaré tu identidad.",
            response_type=MessageResponseType.RETRIEVED,
            access_requirement=AccessRequirement.IDENTITY_VERIFICATION,
            resume_message="Quiero agendar una cita",
        )


class FirstGuidanceOnlyRouter:
    def __init__(self) -> None:
        self.calls: list[str] = []

    async def route(
        self,
        current: MessageCommand,
        manifests: tuple[ModuleManifest, ...],
    ) -> RoutingDecision:
        self.calls.append(current.message)
        if current.message == "mi perro no quiere comer":
            return RoutingDecision.module(
                intent="guidance.ask",
                module_id="veterinary_guidance",
            )
        return RoutingDecision.unknown("no new intent")


def pet_manifest() -> ModuleManifest:
    return ModuleManifest(
        module_id="pet_profile",
        version="1.0.0",
        description="Pet operations",
        intents=("pets.register",),
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
            pending_confirmation=None,
        )
    ]
    assert executor.contexts == [execution_context]
    assert general.commands == []


@pytest.mark.anyio
async def test_pending_confirmation_survives_and_returns_to_the_same_module() -> None:
    general = GeneralProcessor()
    executor = ConfirmingExecutor()
    registry = ModuleRegistry()
    registry.register(manifest(), executor)
    router = Router(RoutingDecision.module(intent="appointments.list", module_id="appointments"))
    graph = build_main_graph(general, registry, router, InMemorySaver())
    first = command()

    first_state = await graph.ainvoke(
        {"command": message_command_to_state(first)},
        config=config(first),
        context=context(),
    )
    second = command(message="sí", idempotency_key="message-002")
    second_state = await graph.ainvoke(
        {"command": message_command_to_state(second)},
        config=config(second),
        context=context(),
    )

    assert first_state["confirmation"]["module_id"] == "appointments"
    assert executor.requests[-1].intent == "appointments.confirmation"
    assert executor.requests[-1].pending_confirmation is not None
    assert executor.requests[-1].pending_confirmation.payload == {"appointment_id": "a-1"}
    assert second_state["confirmation"] is None
    assert router.calls == 1


@pytest.mark.anyio
async def test_expired_pending_operation_does_not_capture_a_new_routable_request() -> None:
    general = GeneralProcessor()
    pet_executor = ExpiredPetRegistrationExecutor()
    appointment_executor = Executor()
    pet_manifest = ModuleManifest(
        module_id="pet_profile",
        version="1.0.0",
        description="Pet profile operations",
        intents=("pets.register", "pet_profile.registration"),
    )
    appointment_manifest = manifest()
    registry = ModuleRegistry()
    registry.register(pet_manifest, pet_executor)
    registry.register(appointment_manifest, appointment_executor)
    router = MessageRouter()
    graph = build_main_graph(general, registry, router, InMemorySaver())
    first = command(message="Registrar una mascota", idempotency_key="message-001")

    first_state = await graph.ainvoke(
        {"command": message_command_to_state(first)},
        config=config(first),
        context=context(),
    )
    second = command(message="Quiero agendar una cita", idempotency_key="message-002")
    second_state = await graph.ainvoke(
        {"command": message_command_to_state(second)},
        config=config(second),
        context=context(),
    )

    assert first_state["confirmation"] is not None
    assert router.calls == ["Registrar una mascota", "Quiero agendar una cita"]
    assert len(pet_executor.requests) == 1
    assert appointment_executor.requests[-1].pending_confirmation is None
    assert second_state["selected_module_id"] == "appointments"


@pytest.mark.anyio
async def test_expired_pending_operation_with_ambiguous_reply_returns_restart_guidance() -> None:
    general = GeneralProcessor()
    pet_executor = ExpiredPetRegistrationExecutor()
    pet_manifest = ModuleManifest(
        module_id="pet_profile",
        version="1.0.0",
        description="Pet profile operations",
        intents=("pets.register", "pet_profile.registration"),
    )
    registry = ModuleRegistry()
    registry.register(pet_manifest, pet_executor)
    router = MessageRouter()
    graph = build_main_graph(general, registry, router, InMemorySaver())
    first = command(message="Registrar una mascota", idempotency_key="message-001")

    await graph.ainvoke(
        {"command": message_command_to_state(first)},
        config=config(first),
        context=context(),
    )
    second = command(message="sí", idempotency_key="message-002")
    second_state = await graph.ainvoke(
        {"command": message_command_to_state(second)},
        config=config(second),
        context=context(),
    )

    result = message_result_from_state(second_state["result"])
    assert router.calls == ["Registrar una mascota", "sí"]
    assert "proceso anterior venció" in (result.message or "").casefold()
    assert general.commands == []
    assert len(pet_executor.requests) == 1


@pytest.mark.anyio
async def test_expired_pending_operation_allows_a_new_general_question() -> None:
    general = GeneralProcessor()
    pet_executor = ExpiredPetRegistrationExecutor()
    pet_manifest = ModuleManifest(
        module_id="pet_profile",
        version="1.0.0",
        description="Pet profile operations",
        intents=("pets.register", "pet_profile.registration"),
    )
    registry = ModuleRegistry()
    registry.register(pet_manifest, pet_executor)
    router = MessageRouter()
    graph = build_main_graph(general, registry, router, InMemorySaver())
    first = command(message="Registrar una mascota", idempotency_key="message-001")

    await graph.ainvoke(
        {"command": message_command_to_state(first)},
        config=config(first),
        context=context(),
    )
    second = command(
        message="¿Qué cuidados necesita un cachorro?",
        idempotency_key="message-002",
    )
    second_state = await graph.ainvoke(
        {"command": message_command_to_state(second)},
        config=config(second),
        context=context(),
    )

    result = message_result_from_state(second_state["result"])
    assert result.message == "general:¿Qué cuidados necesita un cachorro?"
    assert general.commands == [second]
    assert second_state["confirmation"] is None


@pytest.mark.anyio
async def test_telegram_guest_continues_pending_offer_in_its_public_module() -> None:
    general = GeneralProcessor()
    executor = GuestAppointmentOfferExecutor()
    selected_manifest = ModuleManifest(
        module_id="veterinary_guidance",
        version="1.0.0",
        description="Public veterinary guidance",
        intents=("guidance.ask", "guidance.appointment_offer"),
        guest_accessible=True,
    )
    registry = ModuleRegistry()
    registry.register(selected_manifest, executor)
    router = FirstGuidanceOnlyRouter()
    graph = build_main_graph(general, registry, router, InMemorySaver())
    first = command(
        message="mi perro no quiere comer",
        roles=("TelegramGuest",),
        idempotency_key="message-001",
    )

    first_state = await graph.ainvoke(
        {"command": message_command_to_state(first)},
        config=config(first),
        context=context(),
    )
    second = command(
        message="sí, por favor",
        roles=("TelegramGuest",),
        idempotency_key="message-002",
    )
    second_state = await graph.ainvoke(
        {"command": message_command_to_state(second)},
        config=config(second),
        context=context(),
    )

    result = message_result_from_state(second_state["result"])
    assert first_state["confirmation"] is not None
    assert router.calls == ["mi perro no quiere comer"]
    assert executor.requests[-1].intent == "guidance.appointment_offer"
    assert executor.requests[-1].pending_confirmation is not None
    assert result.access_requirement is AccessRequirement.IDENTITY_VERIFICATION
    assert result.resume_message == "Quiero agendar una cita"
    assert general.commands == []


@pytest.mark.anyio
async def test_telegram_guest_cannot_resume_pending_private_module() -> None:
    general = GeneralProcessor()
    executor = ConfirmingExecutor()
    registry = ModuleRegistry()
    registry.register(manifest(), executor)
    router = FixedRouter(RoutingDecision.unknown("no new intent"))
    graph = build_main_graph(general, registry, router, InMemorySaver())
    current = command(message="sí", roles=("TelegramGuest",))
    pending = PendingConfirmation.create(
        module_id="appointments",
        action="appointments.cancel",
        payload={"appointment_id": "a-1"},
        ttl_seconds=600,
        intent="appointments.confirmation",
    )

    state = await graph.ainvoke(
        {
            "command": message_command_to_state(current),
            "confirmation": confirmation_to_state(pending),
        },
        config=config(current),
        context=context(),
    )

    result = message_result_from_state(state["result"])
    assert result.access_requirement is AccessRequirement.IDENTITY_VERIFICATION
    assert state["confirmation"] is None
    assert executor.requests == []
    assert general.commands == []


@pytest.mark.anyio
async def test_telegram_guest_requesting_private_module_requires_identity_verification() -> None:
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

    result = message_result_from_state(state["result"])
    assert result.access_requirement.value == "identity_verification"
    assert "verificar tu identidad" in (result.message or "").casefold()
    assert state["fallback_reason"] == "guest_link_required"
    assert general.commands == []
    assert router.calls == 1
    assert executor.requests == []


@pytest.mark.anyio
async def test_telegram_guest_can_execute_module_explicitly_marked_as_public() -> None:
    general = GeneralProcessor()
    executor = Executor(module_id="services_catalog")
    selected_manifest = ModuleManifest(
        module_id="services_catalog",
        version="1.0.0",
        description="Public veterinary services",
        intents=("services.list",),
        guest_accessible=True,
    )
    registry = ModuleRegistry()
    registry.register(selected_manifest, executor)
    router = PublicModuleRouter(selected_manifest)
    graph = build_main_graph(general, registry, router, InMemorySaver())
    current = command(roles=("TelegramGuest",))

    state = await graph.ainvoke(
        {"command": message_command_to_state(current)},
        config=config(current),
        context=context(),
    )

    result = message_result_from_state(state["result"])
    assert result.module == "services_catalog"
    assert executor.requests[0].intent == "services.list"
    assert general.commands == []


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


@pytest.mark.anyio
async def test_module_handoff_executes_target_and_propagates_continuation() -> None:
    continuation = ModuleContinuation("appointments", "appointments.list")
    source = HandoffExecutor(
        ModuleHandoff(
            target=ModuleContinuation("pet_profile", "pets.register"),
            continuation=continuation,
        )
    )
    target = Executor(module_id="pet_profile")
    registry = ModuleRegistry()
    registry.register(manifest(), source)
    registry.register(pet_manifest(), target)
    graph = build_main_graph(
        GeneralProcessor(),
        registry,
        FixedRouter(RoutingDecision.module(intent="appointments.list", module_id="appointments")),
        InMemorySaver(),
    )
    current = command()

    state = await graph.ainvoke(
        {"command": message_command_to_state(current)},
        config=config(current),
        context=context(),
    )

    result = message_result_from_state(state["result"])
    assert result.module == "pet_profile"
    assert result.message == "Primero registraré tu mascota.\n\nTienes una cita mañana"
    assert state["selected_module_id"] == "pet_profile"
    assert target.requests == [
        ModuleExecutionRequest(
            command=current,
            intent="pets.register",
            manifest=pet_manifest(),
            continuation=continuation,
        )
    ]


@pytest.mark.anyio
async def test_public_module_cannot_handoff_guest_to_private_module() -> None:
    source_manifest = ModuleManifest(
        module_id="veterinary_guidance",
        version="1.0.0",
        description="Public veterinary guidance",
        intents=("guidance.ask",),
        guest_accessible=True,
    )
    source = HandoffExecutor(
        ModuleHandoff(
            target=ModuleContinuation("appointments", "appointments.list")
        ),
        module_id="veterinary_guidance",
    )
    private_target = Executor()
    registry = ModuleRegistry()
    registry.register(source_manifest, source)
    registry.register(manifest(), private_target)
    graph = build_main_graph(
        GeneralProcessor(),
        registry,
        FixedRouter(
            RoutingDecision.module(
                intent="guidance.ask",
                module_id="veterinary_guidance",
            )
        ),
        InMemorySaver(),
    )
    current = command(
        message="mi perro no quiere comer",
        roles=("TelegramGuest",),
    )

    state = await graph.ainvoke(
        {"command": message_command_to_state(current)},
        config=config(current),
        context=context(),
    )

    result = message_result_from_state(state["result"])
    assert result.access_requirement is AccessRequirement.IDENTITY_VERIFICATION
    assert result.module == "veterinary_guidance"
    assert private_target.requests == []


@pytest.mark.anyio
async def test_module_handoff_rejects_an_unregistered_target() -> None:
    source = HandoffExecutor(ModuleHandoff(target=ModuleContinuation("missing", "missing.start")))
    registry = ModuleRegistry()
    registry.register(manifest(), source)
    graph = build_main_graph(
        GeneralProcessor(),
        registry,
        FixedRouter(RoutingDecision.module(intent="appointments.list", module_id="appointments")),
        InMemorySaver(),
    )
    current = command()

    with pytest.raises(GraphCompositionError, match="handoff target"):
        await graph.ainvoke(
            {"command": message_command_to_state(current)},
            config=config(current),
            context=context(),
        )


@pytest.mark.anyio
async def test_module_handoff_rejects_a_cycle() -> None:
    source = HandoffExecutor(
        ModuleHandoff(target=ModuleContinuation("appointments", "appointments.list"))
    )
    registry = ModuleRegistry()
    registry.register(manifest(), source)
    graph = build_main_graph(
        GeneralProcessor(),
        registry,
        FixedRouter(RoutingDecision.module(intent="appointments.list", module_id="appointments")),
        InMemorySaver(),
    )
    current = command()

    with pytest.raises(GraphCompositionError, match="cycle"):
        await graph.ainvoke(
            {"command": message_command_to_state(current)},
            config=config(current),
            context=context(),
        )


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
