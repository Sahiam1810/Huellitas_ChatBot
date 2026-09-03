from app.orchestration.rule_based_intent_router import IntentRule

APPOINTMENTS_ROUTING_RULES = (
    IntentRule(
        "appointments",
        "appointments.book",
        (
            "agendar una cita",
            "agendar cita",
            "reservar una cita",
            "reservar cita",
            "sacar una cita",
            "pedir una cita",
            "quiero una cita",
        ),
    ),
    IntentRule(
        "appointments",
        "appointments.history",
        ("historial de citas", "citas pasadas", "citas anteriores", "citas canceladas"),
    ),
    IntentRule(
        "appointments",
        "appointments.view",
        (
            "detalle de mi cita",
            "cuando es mi cita",
            "cuándo es mi cita",
            "cita de",
            "datos de mi cita",
            "datos de la cita",
            "informacion de mi cita",
            "información de mi cita",
        ),
    ),
    IntentRule(
        "appointments",
        "appointments.list",
        ("mis citas", "que citas tengo", "qué citas tengo", "proximas citas", "próximas citas"),
    ),
    IntentRule(
        "appointments",
        "appointments.cancel",
        (
            "cancelar mi cita",
            "cancelar cita",
            "quiero cancelar mi cita",
            "quiero cancelar la cita",
            "quiero cancelar una cita",
            "anular cita",
            "anular mi cita",
        ),
    ),
    IntentRule(
        "appointments",
        "appointments.reschedule",
        (
            "reprogramar mi cita",
            "reprogramar cita",
            "cambiar mi cita",
            "cambiar fecha de mi cita",
            "reagendar mi cita",
            "mover mi cita",
        ),
    ),
)
