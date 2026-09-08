import re
import unicodedata
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum


class DateResolutionError(StrEnum):
    UNRECOGNIZED = "unrecognized"
    AMBIGUOUS = "ambiguous"
    PAST = "past"
    INVALID = "invalid"


@dataclass(frozen=True, slots=True)
class DateResolution:
    value: date | None = None
    error: DateResolutionError | None = None


BOOKING_DATE_PROMPT = "¿Para qué fecha deseas agendar la cita?"
RESCHEDULE_DATE_PROMPT = "¿Para qué fecha deseas reprogramar la cita?"


def date_resolution_error_message(
    error: DateResolutionError | None,
    prompt: str = BOOKING_DATE_PROMPT,
) -> str:
    if error is DateResolutionError.PAST:
        return "Esa fecha ya pasó. Indica una fecha válida desde hoy en adelante."
    if error is DateResolutionError.INVALID:
        return "Esa fecha no existe. Indica otra fecha válida."
    if error is DateResolutionError.AMBIGUOUS:
        return "No pude determinar una sola fecha. Indica un día más específico."
    return "No entendí la fecha. " + prompt


_WEEKDAYS = {
    "lunes": 0,
    "martes": 1,
    "miercoles": 2,
    "jueves": 3,
    "viernes": 4,
    "sabado": 5,
    "domingo": 6,
}

_MONTHS = {
    "enero": 1,
    "febrero": 2,
    "marzo": 3,
    "abril": 4,
    "mayo": 5,
    "junio": 6,
    "julio": 7,
    "agosto": 8,
    "septiembre": 9,
    "setiembre": 9,
    "octubre": 10,
    "noviembre": 11,
    "diciembre": 12,
}

_MONTH_PATTERN = "|".join(_MONTHS)
_WEEKDAY_PATTERN = "|".join(_WEEKDAYS)


def resolve_appointment_date(text: str, reference_date: date) -> DateResolution:
    normalized = _normalize(text)
    candidates: list[date] = []
    invalid_calendar_date = False

    for match in re.finditer(r"(?<!\d)(\d{4})-(\d{1,2})-(\d{1,2})(?!\d)", normalized):
        candidate = _calendar_date(*map(int, match.groups()))
        invalid_calendar_date |= candidate is None
        if candidate is not None:
            candidates.append(candidate)

    for match in re.finditer(
        r"(?<!\d)(\d{1,2})[/-](\d{1,2})[/-](\d{4})(?!\d)", normalized
    ):
        day, month, year = map(int, match.groups())
        candidate = _calendar_date(year, month, day)
        invalid_calendar_date |= candidate is None
        if candidate is not None:
            candidates.append(candidate)

    without_day_after_tomorrow = normalized
    if re.search(r"\bpasado\s+manana\b", normalized):
        candidates.append(reference_date + timedelta(days=2))
        without_day_after_tomorrow = re.sub(
            r"\bpasado\s+manana\b", " ", normalized
        )
    if re.search(r"\bmanana\b", without_day_after_tomorrow):
        candidates.append(reference_date + timedelta(days=1))
    if re.search(r"\bhoy\b", normalized):
        candidates.append(reference_date)

    weekday_matches = re.findall(rf"\b({_WEEKDAY_PATTERN})\b", normalized)
    if len(set(weekday_matches)) > 1:
        return DateResolution(error=DateResolutionError.AMBIGUOUS)
    if weekday_matches:
        candidates.append(_resolve_weekday(normalized, weekday_matches[0], reference_date))

    next_month_match = re.search(
        r"\b(?:el\s+)?(\d{1,2})\s+(?:de|del)\s+(?:el\s+)?"
        r"(?:proximo|siguiente)\s+mes\b",
        normalized,
    )
    if next_month_match:
        year, month = _next_month(reference_date)
        candidate = _calendar_date(year, month, int(next_month_match.group(1)))
        invalid_calendar_date |= candidate is None
        if candidate is not None:
            candidates.append(candidate)

    this_month_match = re.search(
        r"\b(?:el\s+)?(\d{1,2})\s+(?:de|del)\s+(?:este|el)\s+mes\b",
        normalized,
    )
    if this_month_match:
        candidate = _calendar_date(
            reference_date.year,
            reference_date.month,
            int(this_month_match.group(1)),
        )
        invalid_calendar_date |= candidate is None
        if candidate is not None:
            candidates.append(candidate)

    for match in re.finditer(
        rf"\b(?:el\s+)?(\d{{1,2}})\s+de\s+({_MONTH_PATTERN})"
        r"(?:\s+de\s+(\d{4}))?\b",
        normalized,
    ):
        day_text, month_name, year_text = match.groups()
        year = int(year_text) if year_text is not None else reference_date.year
        candidate = _calendar_date(year, _MONTHS[month_name], int(day_text))
        invalid_calendar_date |= candidate is None
        if candidate is not None:
            candidates.append(candidate)

    distinct_candidates = tuple(dict.fromkeys(candidates))
    if len(distinct_candidates) > 1:
        return DateResolution(error=DateResolutionError.AMBIGUOUS)
    if len(distinct_candidates) == 1:
        candidate = distinct_candidates[0]
        if candidate < reference_date:
            return DateResolution(error=DateResolutionError.PAST)
        return DateResolution(value=candidate)
    if invalid_calendar_date:
        return DateResolution(error=DateResolutionError.INVALID)
    if re.search(r"\b(?:el|dia)\s+\d{1,2}\b", normalized):
        return DateResolution(error=DateResolutionError.AMBIGUOUS)
    return DateResolution(error=DateResolutionError.UNRECOGNIZED)


def _normalize(value: str) -> str:
    decomposed = unicodedata.normalize("NFKD", value.casefold())
    without_accents = "".join(
        character for character in decomposed if not unicodedata.combining(character)
    )
    without_punctuation = re.sub(r"[^a-z0-9\s/-]", " ", without_accents)
    return " ".join(without_punctuation.split())


def _calendar_date(year: int, month: int, day: int) -> date | None:
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _resolve_weekday(text: str, weekday_name: str, reference_date: date) -> date:
    target_weekday = _WEEKDAYS[weekday_name]
    week_start = reference_date - timedelta(days=reference_date.weekday())
    if re.search(r"\b(?:de\s+la\s+)?proxima\s+semana\b", text):
        return week_start + timedelta(days=7 + target_weekday)
    if re.search(rf"\b(?:proximo|siguiente)\s+{weekday_name}\b", text):
        days_ahead = (target_weekday - reference_date.weekday()) % 7
        return reference_date + timedelta(days=days_ahead or 7)
    if re.search(rf"\beste\s+{weekday_name}\b", text):
        return week_start + timedelta(days=target_weekday)
    days_ahead = (target_weekday - reference_date.weekday()) % 7
    return reference_date + timedelta(days=days_ahead)


def _next_month(reference_date: date) -> tuple[int, int]:
    if reference_date.month == 12:
        return reference_date.year + 1, 1
    return reference_date.year, reference_date.month + 1
