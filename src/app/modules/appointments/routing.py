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
        ("detalle de mi cita", "cuando es mi cita", "cuándo es mi cita", "cita de"),
    ),
    IntentRule(
        "appointments",
        "appointments.list",
        ("mis citas", "que citas tengo", "qué citas tengo", "proximas citas", "próximas citas"),
    ),
)
