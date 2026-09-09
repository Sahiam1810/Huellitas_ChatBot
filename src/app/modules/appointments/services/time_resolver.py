import re
import unicodedata
from datetime import time

_EXPLICIT_TIME = re.compile(
    r"\b(?:(?:de\s+)?a\s+las?|de\s+las)\s+"
    r"(\d{1,2})(?::(\d{1,2}))?(?![:\d])"
    r"(?:\s*(?:(?:de\s+la\s+)?(manana|tarde|noche)|([ap])\s*m))?\b"
)


def resolve_appointment_time(text: str) -> time | None:
    match = _EXPLICIT_TIME.search(_normalize(text))
    if match is None:
        return None
    hour_text, minute_text, day_period, meridiem = match.groups()
    hour = int(hour_text)
    minute = int(minute_text or 0)
    if minute > 59:
        return None
    period = meridiem or day_period
    if period is not None:
        if not 1 <= hour <= 12:
            return None
        if period in {"p", "tarde", "noche"} and hour != 12:
            hour += 12
        elif period in {"a", "manana"} and hour == 12:
            hour = 0
    elif hour > 23:
        return None
    return time(hour, minute)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    without_punctuation = re.sub(r"[^a-z0-9:\s]", " ", without_accents)
    return " ".join(without_punctuation.split())
