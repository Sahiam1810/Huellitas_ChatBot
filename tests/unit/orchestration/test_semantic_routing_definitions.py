import pytest

from app.modules.appointments.manifest import APPOINTMENTS_MANIFEST
from app.modules.appointments.semantic_routing import APPOINTMENTS_SEMANTIC_INTENTS
from app.modules.pet_profile.manifest import PET_PROFILE_MANIFEST
from app.modules.pet_profile.semantic_routing import PET_PROFILE_SEMANTIC_INTENTS
from app.modules.preventive_care.manifest import PREVENTIVE_CARE_MANIFEST
from app.modules.preventive_care.semantic_routing import PREVENTIVE_CARE_SEMANTIC_INTENTS
from app.modules.services_catalog.manifest import SERVICES_CATALOG_MANIFEST
from app.modules.services_catalog.semantic_routing import SERVICES_CATALOG_SEMANTIC_INTENTS
from app.modules.veterinary_guidance.manifest import VETERINARY_GUIDANCE_MANIFEST
from app.modules.veterinary_guidance.semantic_routing import (
    VETERINARY_GUIDANCE_SEMANTIC_INTENTS,
)
from app.orchestration.module_manifest import ModuleManifest
from app.orchestration.semantic_intent_router import SemanticIntentDefinition

MODULE_DEFINITIONS = (
    (PET_PROFILE_MANIFEST, PET_PROFILE_SEMANTIC_INTENTS),
    (SERVICES_CATALOG_MANIFEST, SERVICES_CATALOG_SEMANTIC_INTENTS),
    (APPOINTMENTS_MANIFEST, APPOINTMENTS_SEMANTIC_INTENTS),
    (VETERINARY_GUIDANCE_MANIFEST, VETERINARY_GUIDANCE_SEMANTIC_INTENTS),
    (PREVENTIVE_CARE_MANIFEST, PREVENTIVE_CARE_SEMANTIC_INTENTS),
)


@pytest.mark.parametrize(("manifest", "definitions"), MODULE_DEFINITIONS)
def test_semantic_definitions_belong_to_their_module_manifest(
    manifest: ModuleManifest,
    definitions: tuple[SemanticIntentDefinition, ...],
) -> None:
    assert definitions
    assert all(definition.module_id == manifest.module_id for definition in definitions)
    assert all(definition.intent in manifest.intents for definition in definitions)
    assert all(definition.examples for definition in definitions)


def test_semantic_intent_pairs_are_unique_across_modules() -> None:
    definitions = tuple(
        definition
        for _, module_definitions in MODULE_DEFINITIONS
        for definition in module_definitions
    )
    pairs = tuple((definition.module_id, definition.intent) for definition in definitions)

    assert len(pairs) == len(set(pairs))
