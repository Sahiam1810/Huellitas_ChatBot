import re

from app.orchestration.module_executor import PendingConfirmation
from app.orchestration.rule_based_intent_router import normalize_for_routing

APPOINTMENT_OFFER_ACTION = "guidance.offer_appointment"
APPOINTMENT_OFFER_INTENT = "guidance.appointment_offer"

_AFFIRMATIVE_CHOICES = {
    "si",
    "confirmo",
    "de acuerdo",
    "adelante",
    "claro",
    "por supuesto",
    "hagamoslo",
    "me gustaria",
}
_NEGATIVE_CHOICES = {
    "no",
    "cancelar",
    "cancela",
    "ahora no",
    "mejor despues",
    "no gracias",
}
_UNCERTAIN_MARKERS = {"tal vez", "quizas", "de pronto", "no se"}
_UNSAFE_MARKERS = {
    "ignora las instrucciones",
    "ignora instrucciones",
    "prompt",
    "cambia de rol",
    "toma el rol",
}
_SCHEDULING_PATTERN = re.compile(
    r"\b(?:quiero|quisiera|deseo|necesito|podemos|puedes)\b.*"
    r"\b(?:agendar|reservar|programar|sacar)\b"
)
_DATE_PATTERN = re.compile(
    r"^(?:para\s+)?(?:hoy|manana|pasado\s+manana|"
    r"(?:el\s+)?(?:lunes|martes|miercoles|jueves|viernes|sabado|domingo))\b"
)


def create_appointment_offer(ttl_seconds: int) -> PendingConfirmation:
    return PendingConfirmation.create(
        module_id="veterinary_guidance",
        action=APPOINTMENT_OFFER_ACTION,
        payload={},
        ttl_seconds=ttl_seconds,
        intent=APPOINTMENT_OFFER_INTENT,
    )


def appointment_offer_choice(message: str) -> bool | None:
    normalized = normalize_for_routing(message)
    if not normalized or any(marker in normalized for marker in _UNSAFE_MARKERS):
        return None
    if any(marker in normalized for marker in _UNCERTAIN_MARKERS):
        return None

    is_negative = (
        normalized in _NEGATIVE_CHOICES
        or re.search(r"\bno\b", normalized) is not None
    )
    is_explicitly_affirmative = (
        normalized in _AFFIRMATIVE_CHOICES
        or normalized.startswith("si ")
    )
    if is_negative and is_explicitly_affirmative:
        return None
    if is_negative:
        return False
    if (
        is_explicitly_affirmative
        or _SCHEDULING_PATTERN.search(normalized) is not None
        or _DATE_PATTERN.search(normalized) is not None
    ):
        return True
    return None
