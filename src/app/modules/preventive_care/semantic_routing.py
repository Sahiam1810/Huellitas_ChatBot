from app.orchestration.semantic_intent_router import SemanticIntentDefinition

PREVENTIVE_CARE_SEMANTIC_INTENTS = (
    SemanticIntentDefinition(
        "preventive_care",
        "preventive.vaccines",
        (
            "consultar las vacunas registradas de una de mis mascotas",
            "ver el historial de vacunación de mi animal",
        ),
    ),
    SemanticIntentDefinition(
        "preventive_care",
        "preventive.vaccines.upcoming",
        (
            "saber cuándo corresponde la próxima vacuna de mi mascota",
            "consultar el siguiente refuerzo pendiente de mi animal",
        ),
    ),
    SemanticIntentDefinition(
        "preventive_care",
        "preventive.ask",
        (
            "pedir recomendaciones preventivas sobre nutrición o desparasitación",
            "consultar cuidados generales para prevenir enfermedades en mascotas",
        ),
    ),
)
