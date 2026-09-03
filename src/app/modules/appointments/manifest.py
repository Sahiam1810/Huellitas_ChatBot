from app.orchestration.module_manifest import ModuleManifest

APPOINTMENTS_MANIFEST = ModuleManifest(
    module_id="appointments",
    version="2.0.0",
    description="Consulta y agenda citas veterinarias del cliente autenticado",
    intents=(
        "appointments.list",
        "appointments.history",
        "appointments.view",
        "appointments.book",
        "appointments.booking",
    ),
    required_permissions=(),
    allowed_tools=(
        "backend.appointments.mine",
        "backend.appointments.booking.options",
        "backend.appointments.booking.slots",
        "backend.appointments.booking.create",
    ),
    response_types=("retrieved",),
    confirmable_actions=("appointments.book",),
    guest_accessible=False,
)
