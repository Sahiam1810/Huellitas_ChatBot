from app.orchestration.rule_based_intent_router import IntentRule

SERVICES_CATALOG_ROUTING_RULES = (
    IntentRule(
        "services_catalog",
        "services.detail",
        (
            "cuánto cuesta",
            "cuanto cuesta",
            "cuánto vale",
            "cuanto vale",
            "qué precio",
            "que precio",
            "cuánto dura",
            "cuanto dura",
            "duración de",
            "duracion de",
        ),
    ),
    IntentRule(
        "services_catalog",
        "services.list",
        (
            "qué servicios ofrecen",
            "que servicios ofrecen",
            "cuáles servicios",
            "cuales servicios",
            "lista de servicios",
            "servicios disponibles",
        ),
    ),
    IntentRule(
        "services_catalog",
        "services.search",
        (
            "tienen servicio",
            "ofrecen servicio",
            "tienen consulta",
            "ofrecen consulta",
            "hay servicio de",
            "servicio de",
        ),
    ),
)
