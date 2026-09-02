from app.orchestration.rule_based_intent_router import IntentRule

PET_PROFILE_ROUTING_RULES = (
    IntentRule(
        "pet_profile",
        "pets.register",
        (
            "registrar mascota",
            "registrar una mascota",
            "agregar mascota",
            "agregar una mascota",
            "crear mascota",
            "nueva mascota",
        ),
    ),
    IntentRule(
        "pet_profile",
        "pets.update",
        (
            "actualiza el peso",
            "cambia el peso",
            "actualiza la edad",
            "cambia la edad",
            "cambia el nombre",
            "actualiza el nombre",
            "cambia la raza",
            "cambia la especie",
            "actualiza las observaciones",
            "quita las observaciones",
            "es macho",
            "es hembra",
        ),
    ),
    IntentRule(
        "pet_profile",
        "pets.view",
        ("datos de", "perfil de", "información de", "informacion de"),
    ),
    IntentRule(
        "pet_profile",
        "pets.list",
        ("mis mascotas", "qué mascotas tengo", "que mascotas tengo", "lista de mascotas"),
    ),
)
