from app.orchestration.rule_based_intent_router import IntentRule

VETERINARY_GUIDANCE_ROUTING_RULES = (
    IntentRule(
        "veterinary_guidance",
        "guidance.urgent",
        (
            "no respira",
            "convulsion",
            "convulsiones",
            "inconsciente",
            "sangrado abundante",
            "mucha sangre",
            "atropellado",
            "envenenado",
            "atragantado",
        ),
    ),
    IntentRule(
        "veterinary_guidance",
        "guidance.ask",
        (
            "mi perro vomita",
            "mi gato vomita",
            "mi gato no come",
            "mi perro no come",
            "que hago si",
            "qué hago si",
            "es normal que",
            "le duele",
            "tiene diarrea",
            "esta decaido",
            "está decaído",
            "esta decaído",
            "tiene fiebre",
            "no quiere comer",
        ),
    ),
)
