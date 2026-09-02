from app.orchestration.module_manifest import ModuleManifest

PET_PROFILE_MANIFEST = ModuleManifest(
    module_id="pet_profile",
    version="1.0.0",
    description="Consulta, registro y actualización confirmada de mascotas propias",
    intents=(
        "pets.list",
        "pets.view",
        "pets.update",
        "pets.register",
        "pet_profile.confirmation",
        "pet_profile.registration",
    ),
    required_permissions=("pets.self.read", "pets.self.create", "pets.self.update"),
    allowed_tools=(
        "backend.pets.mine",
        "backend.pets.mine.create",
        "backend.species",
        "backend.races",
    ),
    response_types=("retrieved",),
    confirmable_actions=("pets.update", "pets.register"),
)
