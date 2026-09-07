from app.orchestration.semantic_intent_router import SemanticIntentDefinition

VETERINARY_GUIDANCE_SEMANTIC_INTENTS = (
    SemanticIntentDefinition(
        "veterinary_guidance",
        "guidance.ask",
        (
            "pedir orientación general por un síntoma o comportamiento de un animal",
            "saber qué vigilar cuando una mascota se siente mal",
            "consultar una duda general sobre la salud de perros o gatos",
        ),
    ),
    SemanticIntentDefinition(
        "veterinary_guidance",
        "guidance.urgent",
        (
            "mascota en peligro inmediato que necesita atención veterinaria de urgencia",
            "animal inconsciente sin respirar convulsionando o con sangrado abundante",
        ),
    ),
)
