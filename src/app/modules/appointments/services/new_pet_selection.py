import re

from app.orchestration.rule_based_intent_router import normalize_for_routing

_DIRECT_SELECTIONS = {
    "otra",
    "otro",
    "otra mascota",
    "otro animal",
    "no otra",
    "no otro",
    "ninguna",
    "ninguna de esas",
    "ninguno de esos",
}

_NEW_PET_PATTERNS = (
    re.compile(r"\b(?:otra|otro)\s+(?:mascota|animal|perro|perra|gato|gata)\b"),
    re.compile(
        r"\b(?:registrar|agregar|anadir)\b.*\b(?:otra|otro|mascota|animal)\b"
    ),
)

_NEGATED_REGISTRATION_PATTERNS = (
    re.compile(
        r"\b(?:prefiero\s+|mejor\s+)?no\s+"
        r"(?:(?:quiero|deseo|necesito|voy\s+a|puedo)\s+)?"
        r"(?:registrar|agregar|anadir)\b"
    ),
    re.compile(
        r"\b(?:prefiero|quiero|deseo|necesito)\s+no\s+"
        r"(?:registrar|agregar|anadir)\b"
    ),
)


def wants_to_register_another_pet(message: str, existing_pet_count: int) -> bool:
    if existing_pet_count < 0:
        raise ValueError("existing pet count cannot be negative")

    normalized = normalize_for_routing(message)
    if normalized.isdigit():
        return int(normalized) == existing_pet_count + 1
    if any(pattern.search(normalized) for pattern in _NEGATED_REGISTRATION_PATTERNS):
        return False
    if normalized in _DIRECT_SELECTIONS:
        return True
    return any(pattern.search(normalized) for pattern in _NEW_PET_PATTERNS)
