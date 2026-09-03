from uuid import uuid4

import pytest

from app.modules.pet_profile.manifest import PET_PROFILE_MANIFEST
from app.modules.pet_profile.routing import PET_PROFILE_ROUTING_RULES
from app.modules.services_catalog.manifest import SERVICES_CATALOG_MANIFEST
from app.modules.services_catalog.routing import SERVICES_CATALOG_ROUTING_RULES
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


@pytest.mark.anyio
async def test_pet_profile_routes_registration_without_using_general_model() -> None:
    router = RuleBasedIntentRouter(PET_PROFILE_ROUTING_RULES)

    decision = await router.route(
        command("Quiero registrar una mascota"),
        (PET_PROFILE_MANIFEST,),
    )

    assert decision.kind is RoutingKind.MODULE
    assert decision.intent == "pets.register"
    assert decision.module_id == "pet_profile"


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "intent"),
    [
        ("¿Qué servicios ofrecen?", "services.list"),
        ("¿Cuánto cuesta la consulta general?", "services.detail"),
        ("¿Tienen servicio de vacunación?", "services.search"),
        ("¿Ofrecen consulta general?", "services.search"),
    ],
)
async def test_services_catalog_routes_deterministically(message: str, intent: str) -> None:
    router = RuleBasedIntentRouter(SERVICES_CATALOG_ROUTING_RULES)

    decision = await router.route(command(message), (SERVICES_CATALOG_MANIFEST,))

    assert decision.kind is RoutingKind.MODULE
    assert decision.intent == intent
    assert decision.module_id == "services_catalog"
