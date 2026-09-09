import re
import unicodedata
from enum import StrEnum


class ConversationContinuation(StrEnum):
    AFFIRMATIVE = "affirmative"
    NEGATIVE = "negative"
    GRATITUDE = "gratitude"
    ACKNOWLEDGEMENT = "acknowledgement"


_CONTINUATIONS = {
    "si": ConversationContinuation.AFFIRMATIVE,
    "confirmo": ConversationContinuation.AFFIRMATIVE,
    "de acuerdo": ConversationContinuation.AFFIRMATIVE,
    "adelante": ConversationContinuation.AFFIRMATIVE,
    "no": ConversationContinuation.NEGATIVE,
    "cancelar": ConversationContinuation.NEGATIVE,
    "ahora no": ConversationContinuation.NEGATIVE,
    "gracias": ConversationContinuation.GRATITUDE,
    "muchas gracias": ConversationContinuation.GRATITUDE,
    "ok": ConversationContinuation.ACKNOWLEDGEMENT,
    "entendido": ConversationContinuation.ACKNOWLEDGEMENT,
    "listo": ConversationContinuation.ACKNOWLEDGEMENT,
}

_RESPONSES = {
    ConversationContinuation.AFFIRMATIVE: (
        "Entendido. Si deseas agendar una cita, escribe: quiero agendar una cita."
    ),
    ConversationContinuation.NEGATIVE: (
        "Entendido. No iniciaré ninguna acción. "
        "¿Necesitas otra ayuda sobre Huellitas o veterinaria?"
    ),
    ConversationContinuation.GRATITUDE: (
        "Con gusto. ¿Necesitas otra ayuda sobre Huellitas o tu mascota?"
    ),
    ConversationContinuation.ACKNOWLEDGEMENT: (
        "Perfecto. Cuéntame qué necesitas sobre Huellitas o tu mascota."
    ),
}


def detect_conversation_continuation(message: str) -> ConversationContinuation | None:
    return _CONTINUATIONS.get(_normalize(message))


def conversation_continuation_response(
    continuation: ConversationContinuation,
) -> str:
    return _RESPONSES[continuation]


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    return " ".join(re.sub(r"[^a-z0-9]+", " ", without_accents).split())
