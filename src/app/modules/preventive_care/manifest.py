from app.orchestration.module_manifest import ModuleManifest

PREVENTIVE_CARE_MANIFEST = ModuleManifest(
    module_id="preventive_care",
    version="1.0.0",
    description="Consulta de vacunas y orientación preventiva basada en historial y contenido autorizado",
    intents=(
        "preventive.vaccines",
        "preventive.vaccines.upcoming",
        "preventive.vaccines.selecting",
        "preventive.ask",
    ),
    required_permissions=(),
    allowed_tools=(
        "backend.vaccinations.list",
        "backend.pets.mine",
        "knowledge.preventive.retrieve",
    ),
    response_types=("retrieved",),
    confirmable_actions=("preventive.vaccines.select_pet",),
    guest_accessible=False,
)
