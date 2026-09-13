import re

from app.orchestration.rule_based_intent_router import normalize_for_routing

_EMAIL_RE = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")


def parse_identification_number(message: str) -> str | None:
    digits = re.sub(r"\D", "", message)
    if 5 <= len(digits) <= 15:
        return digits
    return None


def parse_owner_full_name(message: str) -> str | None:
    name = message.strip()
    if not name or len(name) > 120:
        return None
    if normalize_for_routing(name) in {"cancelar", "cancela", "cancelo"}:
        return None
    if parse_identification_number(name) is not None and name.replace(" ", "").isdigit():
        return None
    return name


def parse_owner_email(message: str) -> str | None:
    email = message.strip()
    if not email or len(email) > 254:
        return None
    if _EMAIL_RE.match(email) is None:
        return None
    return email.lower()


IDENTIFICATION_PROMPT = "Para continuar, indícame tu número de cédula."
OWNER_NAME_PROMPT = "¿Cuál es tu nombre completo?"
OWNER_EMAIL_PROMPT = "¿Cuál es tu correo electrónico de contacto?"
IDENTIFICATION_INVALID = "La cédula debe tener entre 5 y 15 dígitos. Inténtalo de nuevo."
OWNER_NAME_INVALID = "Indica tu nombre completo (máximo 120 caracteres)."
OWNER_EMAIL_INVALID = "Indica un correo electrónico válido, por ejemplo nombre@correo.com."
OWNER_NOT_FOUND = "No encontré un registro con esa cédula."
