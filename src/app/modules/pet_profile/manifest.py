from app.orchestration.module_manifest import ModuleManifest

PET_PROFILE_MANIFEST = ModuleManifest(
    module_id="pet_profile",
    version="1.0.0",
    description="Consulta y actualización confirmada de mascotas propias",
    intents=("pets.list", "pets.view", "pets.update", "pet_profile.confirmation"),
    required_permissions=("pets.self.read", "pets.self.update"),
    allowed_tools=("backend.pets.mine", "backend.species", "backend.races"),
    response_types=("retrieved",),
    confirmable_actions=("pets.update",),
)
