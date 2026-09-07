from app.orchestration.semantic_intent_router import SemanticIntentDefinition

SERVICES_CATALOG_SEMANTIC_INTENTS = (
    SemanticIntentDefinition(
        "services_catalog",
        "services.list",
        (
            "conocer el catálogo completo de atenciones que presta la veterinaria",
            "saber qué ofrece la clínica para atender animales",
            "consultar las prestaciones veterinarias actualmente disponibles",
        ),
    ),
    SemanticIntentDefinition(
        "services_catalog",
        "services.search",
        (
            "confirmar si la clínica presta una atención veterinaria específica",
            "buscar un procedimiento concreto dentro de la oferta de la veterinaria",
            "averiguar si realizan un servicio particular para una mascota",
        ),
    ),
    SemanticIntentDefinition(
        "services_catalog",
        "services.detail",
        (
            "conocer precio duración y detalles de una atención veterinaria",
            "pedir información detallada sobre un servicio de la clínica",
            "consultar cuánto vale y cuánto tarda un procedimiento",
        ),
    ),
)
