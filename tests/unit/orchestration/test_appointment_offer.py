import pytest

from app.orchestration.appointment_offer import appointment_offer_choice


@pytest.mark.parametrize(
    "message",
    (
        "sí",
        "quiero reservarlo",
        "agéndalo",
        "para mañana",
        "agéndame una",
        "agendame una cita",
        "Agenda me una",
        "reservame una",
    ),
)
def test_appointment_offer_accepts_natural_confirmation(message: str) -> None:
    assert appointment_offer_choice(message) is True


def test_appointment_offer_accepts_natural_rejection() -> None:
    assert appointment_offer_choice("no gracias") is False


def test_appointment_offer_keeps_uncertain_answer_ambiguous() -> None:
    assert appointment_offer_choice("tal vez") is None

