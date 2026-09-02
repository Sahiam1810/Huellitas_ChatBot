from app.modules.pet_profile.contracts_registration import PetRegistrationDraft
from app.ports.pet_profile_gateway import CatalogItem


def registration_prompt(
    draft: PetRegistrationDraft,
    catalog: tuple[CatalogItem, ...] = (),
) -> str:
    if draft.step == "name":
        return "¿Cómo se llama tu mascota?"
    if draft.step == "species":
        return f"¿Cuál es su especie? Opciones: {_catalog_names(catalog)}."
    if draft.step == "race":
        return f"¿Cuál es su raza? Opciones: {_catalog_names(catalog)}."
    if draft.step == "age":
        return "¿Cuántos años tiene? Responde con un número entre 0 y 150."
    if draft.step == "gender":
        return "¿Es macho o hembra?"
    if draft.step == "weight":
        return "¿Cuánto pesa en kilogramos? Por ejemplo: 12.5."
    if draft.step == "observations":
        return "¿Quieres agregar alguna observación? Responde 'ninguna' si no aplica."
    return registration_summary(draft)


def registration_summary(draft: PetRegistrationDraft) -> str:
    observations = draft.observations or "sin observaciones"
    gender = "hembra" if draft.gender == "F" else "macho"
    return (
        f"Registraré a {draft.name}: especie {draft.species_name}, raza {draft.race_name}, "
        f"{draft.age} años, {gender}, {draft.weight:g} kg, {observations}. "
        "¿Confirmas? Responde sí o no."
    )


def _catalog_names(items: tuple[CatalogItem, ...]) -> str:
    return ", ".join(item.name for item in items) or "no hay opciones disponibles"
