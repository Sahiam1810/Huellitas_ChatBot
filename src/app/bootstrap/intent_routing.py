from app.modules.appointments.routing import APPOINTMENTS_ROUTING_RULES
from app.modules.appointments.semantic_routing import APPOINTMENTS_SEMANTIC_INTENTS
from app.modules.pet_profile.routing import PET_PROFILE_ROUTING_RULES
from app.modules.pet_profile.semantic_routing import PET_PROFILE_SEMANTIC_INTENTS
from app.modules.preventive_care.routing import PREVENTIVE_CARE_ROUTING_RULES
from app.modules.preventive_care.semantic_routing import PREVENTIVE_CARE_SEMANTIC_INTENTS
from app.modules.services_catalog.routing import SERVICES_CATALOG_ROUTING_RULES
from app.modules.services_catalog.semantic_routing import SERVICES_CATALOG_SEMANTIC_INTENTS
from app.modules.veterinary_guidance.routing import VETERINARY_GUIDANCE_ROUTING_RULES
from app.modules.veterinary_guidance.semantic_routing import (
    VETERINARY_GUIDANCE_SEMANTIC_INTENTS,
)
from app.orchestration.composite_intent_router import CompositeIntentRouter
from app.orchestration.intent_router import IntentRouter
from app.orchestration.rule_based_intent_router import RuleBasedIntentRouter
from app.orchestration.semantic_intent_router import SemanticIntentRouter
from app.ports.embedding_model import EmbeddingModel

DETERMINISTIC_RULES = (
    PET_PROFILE_ROUTING_RULES
    + SERVICES_CATALOG_ROUTING_RULES
    + APPOINTMENTS_ROUTING_RULES
    + VETERINARY_GUIDANCE_ROUTING_RULES
    + PREVENTIVE_CARE_ROUTING_RULES
)

SEMANTIC_INTENTS = (
    PET_PROFILE_SEMANTIC_INTENTS
    + SERVICES_CATALOG_SEMANTIC_INTENTS
    + APPOINTMENTS_SEMANTIC_INTENTS
    + VETERINARY_GUIDANCE_SEMANTIC_INTENTS
    + PREVENTIVE_CARE_SEMANTIC_INTENTS
)


def build_intent_router(
    embedding_model: EmbeddingModel | None,
    *,
    semantic_enabled: bool,
    minimum_score: float,
    minimum_margin: float,
) -> IntentRouter:
    deterministic = RuleBasedIntentRouter(DETERMINISTIC_RULES)
    if not semantic_enabled or embedding_model is None:
        return deterministic
    semantic = SemanticIntentRouter(
        embedding_model,
        SEMANTIC_INTENTS,
        minimum_score=minimum_score,
        minimum_margin=minimum_margin,
    )
    return CompositeIntentRouter(deterministic, semantic)
