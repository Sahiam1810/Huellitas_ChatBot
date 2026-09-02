from app.modules.pet_profile.graph import PetProfileModuleExecutor
from app.modules.pet_profile.manifest import PET_PROFILE_MANIFEST
from app.orchestration.module_registry import ModuleRegistry
from app.ports.pet_profile_gateway import PetProfileGateway


def build_module_registry(
    pet_profile_gateway: PetProfileGateway | None = None,
    *,
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
    return registry
