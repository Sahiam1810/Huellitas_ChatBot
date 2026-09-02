import re

from app.modules.pet_profile.contracts import PreparedProfileChange
from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.ports.pet_profile_gateway import CatalogItem, PetProfile, PetProfilePatch


def _decimal(value: str) -> float:
    return float(value.replace(",", "."))


def _catalog_match(message: str, label: str, items: tuple[CatalogItem, ...]) -> CatalogItem | None:
    normalized = normalize_for_routing(message)
    if label not in normalized:
        return None
    return next(
        (item for item in items if normalize_for_routing(item.name) in normalized),
        None,
    )


def parse_profile_change(
    message: str,
    pet: PetProfile,
    species: tuple[CatalogItem, ...],
    races: tuple[CatalogItem, ...],
) -> PreparedProfileChange | None:
    normalized = normalize_for_routing(message)
    searchable = message.casefold()
    values: dict[str, object] = {"expected_updated_at": pet.updated_at}
    descriptions: list[str] = []

    weight = re.search(r"peso(?: de [\wáéíóúñ]+)?(?: a| es)?\s+(\d+(?:[.,]\d+)?)", searchable)
    if weight:
        parsed = _decimal(weight.group(1))
        values["weight"] = parsed
        descriptions.append(f"peso: {parsed:g} kg")
    age = re.search(r"edad(?: de [\wáéíóúñ]+)?(?: a| es)?\s+(\d+)", searchable)
    if age:
        parsed_age = int(age.group(1))
        values["age"] = parsed_age
        descriptions.append(f"edad: {parsed_age} años")
    name = re.search(r"(?:nombre de [a-z0-9]+|nombre)(?: a| es)?\s+([a-z0-9]+)$", normalized)
    if name:
        parsed_name = name.group(1).title()
        values["name"] = parsed_name
        descriptions.append(f"nombre: {parsed_name}")
    if "hembra" in normalized:
        values["gender"] = "F"
        descriptions.append("género: hembra")
    elif "macho" in normalized:
        values["gender"] = "M"
        descriptions.append("género: macho")
    clear_observations = "observacion" in normalized and any(
        action in normalized for action in ("quita", "elimina", "borra", "limpia")
    )
    observations = re.search(r"observaciones?(?: de [a-z0-9]+)?(?: a| son|:)?\s+(.+)$", normalized)
    if clear_observations:
        values["observations"] = None
        values["change_observations"] = True
        descriptions.append("observaciones: sin observaciones")
    elif observations:
        text = observations.group(1).strip()
        values["observations"] = text
        values["change_observations"] = True
        descriptions.append(f"observaciones: {text}")
    selected_species = _catalog_match(message, "especie", species)
    if selected_species is not None:
        values["species_id"] = selected_species.id
        descriptions.append(f"especie: {selected_species.name}")
    selected_race = _catalog_match(message, "raza", races)
    if selected_race is not None:
        values["race_id"] = selected_race.id
        descriptions.append(f"raza: {selected_race.name}")
    if not descriptions:
        return None
    return PreparedProfileChange(PetProfilePatch(**values), tuple(descriptions))
