from app.orchestration.module_manifest import ModuleManifest

APPOINTMENTS_MANIFEST = ModuleManifest(
    module_id="appointments",
    version="1.0.0",
    description="Consulta las citas veterinarias del cliente autenticado",
    intents=("appointments.list", "appointments.history", "appointments.view"),
    required_permissions=(),
    allowed_tools=("backend.appointments.mine",),
    response_types=("retrieved",),
    confirmable_actions=(),
    guest_accessible=False,
)
