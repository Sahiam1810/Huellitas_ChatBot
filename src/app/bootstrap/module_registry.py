from app.modules.appointments.graph import AppointmentsModuleExecutor
from app.modules.appointments.manifest import APPOINTMENTS_MANIFEST
from app.modules.pet_profile.graph import PetProfileModuleExecutor
from app.modules.pet_profile.manifest import PET_PROFILE_MANIFEST
from app.modules.services_catalog.graph import ServicesCatalogModuleExecutor
from app.modules.services_catalog.manifest import SERVICES_CATALOG_MANIFEST
from app.modules.veterinary_guidance.graph import VeterinaryGuidanceModuleExecutor
from app.modules.veterinary_guidance.manifest import VETERINARY_GUIDANCE_MANIFEST
from app.orchestration.module_registry import ModuleRegistry
from app.ports.appointments_gateway import AppointmentsGateway
from app.ports.guidance_knowledge_gateway import GuidanceKnowledgeGateway
from app.ports.pet_profile_gateway import PetProfileGateway
from app.ports.service_knowledge_gateway import ServiceKnowledgeGateway
from app.ports.services_catalog_gateway import ServicesCatalogGateway


def build_module_registry(
    pet_profile_gateway: PetProfileGateway | None = None,
    *,
    services_catalog_gateway: ServicesCatalogGateway | None = None,
    service_knowledge_gateway: ServiceKnowledgeGateway | None = None,
    guidance_knowledge_gateway: GuidanceKnowledgeGateway | None = None,
    appointments_gateway: AppointmentsGateway | None = None,
    display_time_zone: str = "America/Bogota",
    confirmation_ttl_seconds: int = 600,
    appointment_booking_ttl_seconds: int = 600,
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
    if appointments_gateway is not None:
        registry.register(
            APPOINTMENTS_MANIFEST,
            AppointmentsModuleExecutor(
                appointments_gateway,
                display_time_zone,
                booking_ttl_seconds=appointment_booking_ttl_seconds,
            ),
        )
    if (
        pet_profile_gateway is not None
        or services_catalog_gateway is not None
        or appointments_gateway is not None
    ):
        registry.register(
            VETERINARY_GUIDANCE_MANIFEST,
            VeterinaryGuidanceModuleExecutor(knowledge_gateway=guidance_knowledge_gateway),
        )
    return registry
