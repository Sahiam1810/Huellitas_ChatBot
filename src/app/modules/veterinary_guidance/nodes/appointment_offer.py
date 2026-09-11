from app.orchestration.module_executor import PendingConfirmation

APPOINTMENT_OFFER_ACTION = "guidance.offer_appointment"
APPOINTMENT_OFFER_INTENT = "guidance.appointment_offer"


def create_appointment_offer(ttl_seconds: int) -> PendingConfirmation:
    return PendingConfirmation.create(
        module_id="veterinary_guidance",
        action=APPOINTMENT_OFFER_ACTION,
        payload={},
        ttl_seconds=ttl_seconds,
        intent=APPOINTMENT_OFFER_INTENT,
    )
