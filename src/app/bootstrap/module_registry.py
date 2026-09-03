from app.modules.pet_profile.graph import PetProfileModuleExecutor
from app.modules.pet_profile.manifest import PET_PROFILE_MANIFEST
from app.modules.services_catalog.graph import ServicesCatalogModuleExecutor
from app.modules.services_catalog.manifest import SERVICES_CATALOG_MANIFEST
from app.orchestration.module_registry import ModuleRegistry
from app.ports.pet_profile_gateway import PetProfileGateway
from app.ports.service_knowledge_gateway import ServiceKnowledgeGateway
from app.ports.services_catalog_gateway import ServicesCatalogGateway


def build_module_registry(
    pet_profile_gateway: PetProfileGateway | None = None,
    *,
    services_catalog_gateway: ServicesCatalogGateway | None = None,
    service_knowledge_gateway: ServiceKnowledgeGateway | None = None,
    confirmation_ttl_seconds: int = 600,
) -> ModuleRegistry:
    registry = ModuleRegistry()
    if pet_profile_gateway is not None:
        registry.register(
            PET_PROFILE_MANIFEST,
            PetProfileModuleExecutor(
                pet_profile_gateway,
                confirmation_ttl_seconds=confirmation_ttl_seconds,
            ),
        )
    if services_catalog_gateway is not None:
        registry.register(
            SERVICES_CATALOG_MANIFEST,
            ServicesCatalogModuleExecutor(
                services_catalog_gateway,
                knowledge_gateway=service_knowledge_gateway,
            ),
        )
    return registry
