from datetime import date

import pytest

from app.modules.appointments.services.date_resolver import (
    DateResolutionError,
    resolve_appointment_date,
)

REFERENCE_DATE = date(2026, 9, 8)


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("la necesito para mañana", date(2026, 9, 9)),
        ("puede ser pasado mañana", date(2026, 9, 10)),
        ("el martes de la próxima semana", date(2026, 9, 15)),
        ("el próximo viernes", date(2026, 9, 11)),
        ("este domingo", date(2026, 9, 13)),
        ("el lunes", date(2026, 9, 14)),
        ("viernes a las 10 de la mañana", date(2026, 9, 11)),
        ("mañana a las 10 de la mañana", date(2026, 9, 9)),
    ],
)
def test_resolves_relative_spanish_dates(text: str, expected: date) -> None:
    result = resolve_appointment_date(text, REFERENCE_DATE)

    assert result.value == expected
    assert result.error is None


@pytest.mark.parametrize(
    ("text", "reference_date", "expected"),
    [
        ("la necesito para 2026-09-20", REFERENCE_DATE, date(2026, 9, 20)),
        ("puede ser el 20/09/2026 por favor", REFERENCE_DATE, date(2026, 9, 20)),
        ("quiero el 20-09-2026", REFERENCE_DATE, date(2026, 9, 20)),
        ("el 15 de este mes", REFERENCE_DATE, date(2026, 9, 15)),
        ("el 15 del próximo mes", REFERENCE_DATE, date(2026, 10, 15)),
        ("el 15 de septiembre", REFERENCE_DATE, date(2026, 9, 15)),
        ("11 de septiembre a las 10 de la mañana", REFERENCE_DATE, date(2026, 9, 11)),
        ("el 3 de enero de 2027", REFERENCE_DATE, date(2027, 1, 3)),
        ("el 10 del próximo mes", date(2026, 12, 20), date(2027, 1, 10)),
    ],
)
def test_resolves_calendar_dates(
    text: str,
    reference_date: date,
    expected: date,
) -> None:
    result = resolve_appointment_date(text, reference_date)

    assert result.value == expected
    assert result.error is None


@pytest.mark.parametrize(
    ("text", "expected_error"),
    [
        ("el 5 de este mes", DateResolutionError.PAST),
        ("el 15 de agosto", DateResolutionError.PAST),
        ("el 31 de febrero", DateResolutionError.INVALID),
        ("quiero una cita el 15", DateResolutionError.AMBIGUOUS),
        ("cuando se pueda", DateResolutionError.UNRECOGNIZED),
    ],
)
def test_rejects_unsafe_or_unclear_dates(
    text: str,
    expected_error: DateResolutionError,
) -> None:
    result = resolve_appointment_date(text, REFERENCE_DATE)

    assert result.value is None
    assert result.error is expected_error
