from app.orchestration.rule_based_intent_router import IntentRule

APPOINTMENTS_ROUTING_RULES = (
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
