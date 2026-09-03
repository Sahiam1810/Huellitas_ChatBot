from app.orchestration.rule_based_intent_router import IntentRule

PREVENTIVE_CARE_ROUTING_RULES = (
    IntentRule(
        "preventive_care",
        "preventive.vaccines.upcoming",
        (
            "proxima vacuna",
            "próxima vacuna",
            "cuando le toca vacuna",
            "cuándo le toca vacuna",
            "refuerzo de vacuna",
            "proximo refuerzo",
            "próximo refuerzo",
        ),
    ),
    IntentRule(
        "preventive_care",
        "preventive.vaccines",
        (
            "vacunas de",
            "historial de vacunas",
            "que vacunas tiene",
            "qué vacunas tiene",
            "mis vacunas",
            "registro de vacunas",
        ),
    ),
    IntentRule(
        "preventive_care",
        "preventive.ask",
        (
            "desparasitacion",
            "desparasitación",
            "desparasitar",
            "cuidados preventivos",
            "nutricion",
            "nutrición",
            "alimentacion",
            "alimentación",
            "calendario de vacunas",
            "cuidado preventivo",
        ),
    ),
)
