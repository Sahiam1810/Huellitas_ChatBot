from datetime import time

import pytest

from app.modules.appointments.services.time_resolver import resolve_appointment_time


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("viernes a las 10 de la mañana", time(10, 0)),
        ("11 de septiembre a las 10:30 a. m.", time(10, 30)),
        ("el viernes a las 3 de la tarde", time(15, 0)),
        ("quiero el cupo de las 7 pm", time(19, 0)),
        ("puede ser a la 1 de la tarde", time(13, 0)),
    ],
)
def test_resolves_explicit_natural_appointment_time(text: str, expected: time) -> None:
    assert resolve_appointment_time(text) == expected


@pytest.mark.parametrize(
    "text",
    (
        "viernes",
        "11 de septiembre",
        "quiero agendar una cita",
        "a las 25 de la tarde",
        "a las 10:75",
    ),
)
def test_does_not_infer_missing_or_invalid_time(text: str) -> None:
    assert resolve_appointment_time(text) is None
