from dataclasses import dataclass

from app.orchestration.rule_based_intent_router import normalize_for_routing

URGENCY_SIGNALS: tuple[str, ...] = (
    "no respira",
    "convulsion",
    "convulsiones",
    "convulsiona",
    "inconsciente",
    "no se mueve",
    "sangrado abundante",
    "mucha sangre",
    "atropellado",
    "envenenado",
    "enveneno",
    "veneno",
    "toxico",
    "distension abdominal",
    "abdomen duro",
    "no orina",
    "atragantado",
    "golpe en la cabeza",
)


@dataclass(frozen=True, slots=True)
class UrgencyAssessment:
    is_urgent: bool
    matched_signals: tuple[str, ...]


def detect_urgency(message: str) -> UrgencyAssessment:
    normalized = normalize_for_routing(message)
    matched = tuple(signal for signal in URGENCY_SIGNALS if signal in normalized)
    return UrgencyAssessment(is_urgent=bool(matched), matched_signals=matched)
