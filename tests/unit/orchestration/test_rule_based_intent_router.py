from uuid import uuid4

import pytest

from app.orchestration.intent_router import RoutingKind
from app.orchestration.message_processor import MessageCommand
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.rule_based_intent_router import IntentRule, RuleBasedIntentRouter


def command(message: str) -> MessageCommand:
    return MessageCommand(
        message=message,
        conversation_id=uuid4(),
        user_id=uuid4(),
        pet_id=None,
        channel="telegram",
        language="es-CO",
        roles=("Cliente",),
        is_escalated=False,
        correlation_id=uuid4(),
        idempotency_key="route-1",
    )


@pytest.mark.anyio
async def test_router_normalizes_accents_and_selects_module_rule() -> None:
    router = RuleBasedIntentRouter(
        (IntentRule("pet_profile", "pets.list", ("mis mascotas", "qué mascotas tengo")),)
    )
    manifests = (ModuleManifest("pet_profile", "1.0.0", "Pets", intents=("pets.list",)),)

    decision = await router.route(command("¿QUE MASCOTAS tengo?"), manifests)

    assert decision.kind is RoutingKind.MODULE
    assert decision.intent == "pets.list"
    assert decision.module_id == "pet_profile"


@pytest.mark.anyio
async def test_router_returns_unknown_when_no_rule_matches() -> None:
    router = RuleBasedIntentRouter(
        (IntentRule("pet_profile", "pets.list", ("mis mascotas",)),)
    )

    decision = await router.route(command("hola"), ())

    assert decision.kind is RoutingKind.UNKNOWN
