BOOKING_START_INTENT = "appointments.book"
BOOKING_CONTINUATION_INTENT = "appointments.booking"


def is_booking_start(intent: str) -> bool:
    return intent == BOOKING_START_INTENT


def is_booking_continuation(intent: str) -> bool:
    return intent == BOOKING_CONTINUATION_INTENT
