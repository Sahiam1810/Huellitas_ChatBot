import pytest

from app.modules.veterinary_guidance.domain.urgency_signals import detect_urgency


@pytest.mark.parametrize(
    "message,expected_signal",
    [
        ("mi perro no respira", "no respira"),
        ("tiene CONVULSIONES", "convulsiones"),
        ("está inconsciente", "inconsciente"),
        ("hay mucha sangre", "mucha sangre"),
        ("fue atropellado", "atropellado"),
        ("creo que se envenenó", "enveneno"),
    ],
)
def test_detect_urgency_matches_critical_signals(message: str, expected_signal: str) -> None:
    result = detect_urgency(message)
    assert result.is_urgent is True
    assert expected_signal in result.matched_signals


def test_detect_urgency_ignores_benign_symptoms() -> None:
    result = detect_urgency("mi gato vomitó una vez hoy")
    assert result.is_urgent is False
    assert result.matched_signals == ()


def test_detect_urgency_is_accent_insensitive() -> None:
    result = detect_urgency("Mi perro tiene convulsión")
    assert result.is_urgent is True
    assert "convulsion" in result.matched_signals
