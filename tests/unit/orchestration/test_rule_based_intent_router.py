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
        ("Quiero saber que servicios tienen", "services.list"),
        ("¿Cuánto cuesta la consulta general?", "services.detail"),
        ("¿Tienen servicio de vacunación?", "services.search"),
        ("¿Ofrecen consulta general?", "services.search"),
        # Ticket 4: frases naturales que antes caían al mensaje genérico de alcance.
        ("¿Qué servicios manejan?", "services.list"),
        ("¿Qué manejan por aquí?", "services.list"),
        ("¿Qué servicios hay?", "services.list"),
        ("¿Qué hacen en Huellitas?", "services.list"),
        ("¿Qué atienden en la veterinaria?", "services.list"),
        ("¿Qué me pueden ofrecer para mi perro?", "services.list"),
        ("¿Cuánto sale la consulta general?", "services.detail"),
        ("¿Cuál es el precio de la vacunación?", "services.detail"),
        ("¿Cuál es el valor de la desparasitación?", "services.detail"),
        ("¿Manejan servicio de peluquería?", "services.search"),
        ("¿Hacen consulta de urgencias?", "services.search"),
        ("¿Atienden servicio de cirugía?", "services.search"),
    ],
)
async def test_services_catalog_routes_deterministically(message: str, intent: str) -> None:
    router = RuleBasedIntentRouter(SERVICES_CATALOG_ROUTING_RULES)

    decision = await router.route(command(message), (SERVICES_CATALOG_MANIFEST,))

    assert decision.kind is RoutingKind.MODULE
    assert decision.intent == intent
    assert decision.module_id == "services_catalog"


@pytest.mark.anyio
async def test_services_catalog_new_phrases_do_not_collide_across_the_full_rule_set() -> None:
    # Guards against ambiguity once every module's rules are combined, as they are
    # in production (app.bootstrap.intent_routing.DETERMINISTIC_RULES).
    from app.bootstrap.intent_routing import DETERMINISTIC_RULES
    from app.modules.appointments.manifest import APPOINTMENTS_MANIFEST
    from app.modules.preventive_care.manifest import PREVENTIVE_CARE_MANIFEST
    from app.modules.veterinary_guidance.manifest import VETERINARY_GUIDANCE_MANIFEST

    router = RuleBasedIntentRouter(DETERMINISTIC_RULES)
    manifests = (
        PET_PROFILE_MANIFEST,
        SERVICES_CATALOG_MANIFEST,
        APPOINTMENTS_MANIFEST,
        VETERINARY_GUIDANCE_MANIFEST,
        PREVENTIVE_CARE_MANIFEST,
    )

    for message in (
        "¿Qué servicios manejan?",
        "¿Qué manejan por aquí?",
        "¿Qué servicios hay?",
        "¿Qué hacen en Huellitas?",
        "¿Qué atienden en la veterinaria?",
        "¿Qué me pueden ofrecer para mi perro?",
        "¿Manejan servicio de peluquería?",
        "¿Hacen consulta de urgencias?",
        "¿Atienden servicio de cirugía?",
    ):
        decision = await router.route(command(message), manifests)
        assert decision.kind is RoutingKind.MODULE
        assert decision.module_id == "services_catalog"
