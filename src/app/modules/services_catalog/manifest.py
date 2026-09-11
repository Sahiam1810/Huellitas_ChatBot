from app.orchestration.module_manifest import ModuleManifest

SERVICES_CATALOG_MANIFEST = ModuleManifest(
    module_id="services_catalog",
    version="1.0.0",
    description="Consulta el catálogo público de servicios veterinarios activos",
    intents=(
        "services.list",
        "services.search",
        "services.detail",
        "services.selecting",
        "services.appointment_offer",
    ),
    required_permissions=(),
    allowed_tools=("backend.services.available", "knowledge.services.describe"),
    response_types=("retrieved",),
    confirmable_actions=("services.select", "services.offer_appointment"),
    guest_accessible=True,
)
