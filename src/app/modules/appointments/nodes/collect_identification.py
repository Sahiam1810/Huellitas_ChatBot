from app.modules.appointments.services.owner_contact import (
    IDENTIFICATION_INVALID,
    IDENTIFICATION_PROMPT,
    parse_identification_number,
)
from app.orchestration.module_executor import PendingConfirmation

QUERY_IDENTIFICATION_ACTION = "appointments.query.collect_id"
CANCEL_IDENTIFICATION_ACTION = "appointments.cancel.collect_id"
RESCHEDULE_IDENTIFICATION_ACTION = "appointments.reschedule.collect_id"


def start_identification_pending(
    *,
    module_id: str,
    action: str,
    intent: str,
    ttl_seconds: int,
    payload: dict[str, object] | None = None,
) -> tuple[str, PendingConfirmation]:
    pending = PendingConfirmation.create(
        module_id=module_id,
        action=action,
        payload=payload or {},
        ttl_seconds=ttl_seconds,
        intent=intent,
    )
    return IDENTIFICATION_PROMPT, pending


def resolve_identification(message: str) -> tuple[str | None, str | None]:
    identification = parse_identification_number(message)
    if identification is None:
        return None, IDENTIFICATION_INVALID
    return identification, None
