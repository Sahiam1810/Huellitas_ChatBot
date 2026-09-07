from app.orchestration.semantic_intent_router import SemanticIntentDefinition

PET_PROFILE_SEMANTIC_INTENTS = (
    SemanticIntentDefinition(
        "pet_profile",
        "pets.list",
        (
            "consultar cuáles mascotas pertenecen a mi perfil",
            "ver todos los animales que tengo registrados",
        ),
    ),
    SemanticIntentDefinition(
        "pet_profile",
        "pets.view",
        (
            "consultar la ficha y los datos de una de mis mascotas",
            "ver la información registrada de mi animal",
        ),
    ),
    SemanticIntentDefinition(
        "pet_profile",
        "pets.update",
        (
            "corregir o actualizar los datos de una mascota registrada",
            "cambiar peso edad nombre raza sexo u observaciones de mi animal",
        ),
    ),
    SemanticIntentDefinition(
        "pet_profile",
        "pets.register",
        (
            "registrar una nueva mascota en mi cuenta",
            "crear el perfil de un animal que me pertenece",
        ),
    ),
)
