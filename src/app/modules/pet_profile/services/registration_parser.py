import re
from dataclasses import dataclass, replace

from app.modules.pet_profile.contracts_registration import PetRegistrationDraft
from app.orchestration.rule_based_intent_router import normalize_for_routing
from app.ports.pet_profile_gateway import CatalogItem


_NAME_INTRODUCTION = re.compile(
    r"(?:\bmi\s+mascota\s+)?\bse\s+llama\s+([^,.!?\n]+)[.!?]?\s*$",
    re.IGNORECASE,
)


@dataclass(frozen=True, slots=True)
class RegistrationAdvance:
    draft: PetRegistrationDraft
    accepted: bool
    error: str | None = None


def advance_registration(
    draft: PetRegistrationDraft,
    message: str,
    species: tuple[CatalogItem, ...] = (),
    races: tuple[CatalogItem, ...] = (),
) -> RegistrationAdvance:
    text = message.strip()
    if draft.step == "name":
        name = _pet_name(text)
        if not name or len(name) > 50:
            return _invalid(draft, "Indica un nombre de máximo 50 caracteres.")
        return _accepted(replace(draft, name=name, step="species"))
    if draft.step == "species":
        item = _catalog_match(text, species)
        if item is None:
            return _invalid(draft, "La especie no coincide con el catálogo disponible.")
        return _accepted(
            replace(draft, species_id=item.id, species_name=item.name, step="race")
        )
    if draft.step == "race":
        item = _catalog_match(text, races)
        if item is None:
            return _invalid(draft, "La raza no coincide con el catálogo disponible.")
        return _accepted(replace(draft, race_id=item.id, race_name=item.name, step="age"))
    if draft.step == "age":
        if not text.isdecimal() or not 0 <= int(text) <= 150:
            return _invalid(draft, "Indica la edad en años con un número entre 0 y 150.")
        return _accepted(replace(draft, age=int(text), step="gender"))
    if draft.step == "gender":
        gender = _gender(text)
        if gender is None:
            return _invalid(draft, "Responde macho o hembra.")
        return _accepted(replace(draft, gender=gender, step="weight"))
    if draft.step == "weight":
        weight = _weight(text)
        if weight is None:
            return _invalid(draft, "Indica un peso entre 0.01 y 500 kg, por ejemplo 12.5.")
        return _accepted(replace(draft, weight=weight, step="observations"))
    if draft.step == "observations":
        normalized = normalize_for_routing(text)
        observations = None if normalized in {"ninguna", "ninguno", "no"} else text
        if observations is not None and (not observations or len(observations) > 500):
            return _invalid(draft, "Las observaciones deben tener máximo 500 caracteres.")
        return _accepted(
            replace(draft, observations=observations, step="confirmation")
        )
    return _invalid(draft, "El registro ya está listo para confirmar.")


def _pet_name(message: str) -> str:
    match = _NAME_INTRODUCTION.search(message)
    return match.group(1).strip() if match is not None else message


def _catalog_match(message: str, items: tuple[CatalogItem, ...]) -> CatalogItem | None:
    normalized = normalize_for_routing(message)
    matches = [item for item in items if normalize_for_routing(item.name) == normalized]
    return matches[0] if len(matches) == 1 else None


def _gender(message: str) -> str | None:
    normalized = normalize_for_routing(message)
    if normalized in {"m", "macho", "masculino"}:
        return "M"
    if normalized in {"f", "hembra", "femenino"}:
        return "F"
    return None


def _weight(message: str) -> float | None:
    match = re.fullmatch(r"\s*(\d+(?:[.,]\d+)?)\s*(?:kg|kilos?)?\s*", message.casefold())
    if match is None:
        return None
    value = float(match.group(1).replace(",", "."))
    return value if 0.01 <= value <= 500 else None


def _accepted(draft: PetRegistrationDraft) -> RegistrationAdvance:
    return RegistrationAdvance(draft=draft, accepted=True)


def _invalid(draft: PetRegistrationDraft, error: str) -> RegistrationAdvance:
    return RegistrationAdvance(draft=draft, accepted=False, error=error)
