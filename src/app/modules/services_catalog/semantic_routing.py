from app.orchestration.semantic_intent_router import SemanticIntentDefinition

SERVICES_CATALOG_SEMANTIC_INTENTS = (
    SemanticIntentDefinition(
        "services_catalog",
        "services.list",
        (
            "quiero ver la lista completa de servicios veterinarios",
            "muéstrame el catálogo de servicios disponibles",
            "qué servicios ofrecen en la veterinaria",
            "listado de prestaciones del catálogo oficial",
            "cuáles son los servicios que tienen disponibles",
            "dame el menú de servicios de la clínica",
        ),
    ),
    SemanticIntentDefinition(
        "services_catalog",
        "services.search",
        (
            "confirmar si la clínica presta una atención veterinaria específica",
            "buscar un procedimiento concreto dentro de la oferta de la veterinaria",
            "averiguar si realizan un servicio particular para una mascota",
            "preguntar si la veterinaria maneja un examen o procedimiento específico",
            "confirmar si ofrecen ecografías radiografías u otra atención concreta",
            "buscar una prestación particular en el catálogo oficial",
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
