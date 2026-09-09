from app.orchestration.module_executor import PendingConfirmation
from app.orchestration.rule_based_intent_router import normalize_for_routing

APPOINTMENT_OFFER_ACTION = "guidance.offer_appointment"
APPOINTMENT_OFFER_INTENT = "guidance.appointment_offer"

_AFFIRMATIVE_CHOICES = {"si", "confirmo", "de acuerdo", "adelante"}
_NEGATIVE_CHOICES = {"no", "cancelar", "cancela", "ahora no"}


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
    if normalized in _AFFIRMATIVE_CHOICES:
        return True
    if normalized in _NEGATIVE_CHOICES:
        return False
    return None
