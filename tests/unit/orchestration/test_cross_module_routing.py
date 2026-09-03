from uuid import uuid4

import pytest

from app.modules.appointments.manifest import APPOINTMENTS_MANIFEST
from app.modules.appointments.routing import APPOINTMENTS_ROUTING_RULES
from app.modules.pet_profile.manifest import PET_PROFILE_MANIFEST
from app.modules.pet_profile.routing import PET_PROFILE_ROUTING_RULES
from app.modules.preventive_care.manifest import PREVENTIVE_CARE_MANIFEST
from app.modules.preventive_care.routing import PREVENTIVE_CARE_ROUTING_RULES
from app.modules.services_catalog.manifest import SERVICES_CATALOG_MANIFEST
from app.modules.services_catalog.routing import SERVICES_CATALOG_ROUTING_RULES
from app.orchestration.intent_router import RoutingKind
from app.orchestration.message_processor import MessageCommand
from app.orchestration.rule_based_intent_router import RuleBasedIntentRouter

COMBINED_RULES = (
    PET_PROFILE_ROUTING_RULES
    + SERVICES_CATALOG_ROUTING_RULES
    + APPOINTMENTS_ROUTING_RULES
    + PREVENTIVE_CARE_ROUTING_RULES
)

COMBINED_MANIFESTS = (
    PET_PROFILE_MANIFEST,
    SERVICES_CATALOG_MANIFEST,
    APPOINTMENTS_MANIFEST,
    PREVENTIVE_CARE_MANIFEST,
)


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
        idempotency_key="route-cross-1",
    )


@pytest.mark.anyio
@pytest.mark.parametrize(
    ("message", "module_id", "intent"),
    [
        ("¿Tienen vacunación?", "preventive_care", "preventive.vaccines"),
        ("¿Tienen vacunas para Luna?", "preventive_care", "preventive.vaccines"),
        ("¿Tienen servicio de baño?", "services_catalog", "services.search"),
        ("¿Ofrecen consulta general?", "services_catalog", "services.search"),
        ("Datos de Luna", "pet_profile", "pets.view"),
        ("Datos de mi cita", "appointments", "appointments.view"),
        ("Quiero cancelar mi cita", "appointments", "appointments.cancel"),
    ],
)
async def test_cross_module_routing_prefers_specific_phrases(
    message: str, module_id: str, intent: str
) -> None:
    decision = await RuleBasedIntentRouter(COMBINED_RULES).route(
        command(message), COMBINED_MANIFESTS
    )
    assert decision.kind is RoutingKind.MODULE
    assert decision.module_id == module_id
    assert decision.intent == intent


@pytest.mark.anyio
async def test_bare_quiero_cancelar_does_not_force_appointments_cancel() -> None:
    decision = await RuleBasedIntentRouter(COMBINED_RULES).route(
        command("Quiero cancelar"), COMBINED_MANIFESTS
    )
    assert not (
        decision.kind is RoutingKind.MODULE
        and decision.module_id == "appointments"
        and decision.intent == "appointments.cancel"
    )
