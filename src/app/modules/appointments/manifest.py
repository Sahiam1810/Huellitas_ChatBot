from app.orchestration.module_manifest import ModuleManifest

APPOINTMENTS_MANIFEST = ModuleManifest(
    module_id="appointments",
    version="3.0.0",
    description="Consulta, agendamiento, cancelación y reprogramación de citas veterinarias",
    intents=(
        "appointments.list",
        "appointments.history",
        "appointments.view",
        "appointments.book",
        "appointments.booking",
        "appointments.cancel",
        "appointments.canceling",
        "appointments.reschedule",
        "appointments.rescheduling",
    ),
    required_permissions=(),
    allowed_tools=(
        "backend.appointments.mine",
        "backend.appointments.booking.options",
        "backend.appointments.booking.slots",
        "backend.appointments.booking.create",
        "backend.appointments.mine.cancel",
        "backend.appointments.mine.request-code",
        "backend.appointments.mine.confirm-code",
    ),
    response_types=("retrieved",),
    confirmable_actions=("appointments.book", "appointments.cancel", "appointments.reschedule"),
    guest_accessible=True,
    guest_requires_identification=True,
)
