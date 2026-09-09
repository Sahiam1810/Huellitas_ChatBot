import pytest

from app.modules.appointments.services.new_pet_selection import (
    wants_to_register_another_pet,
)


@pytest.mark.parametrize(
    ("message", "count"),
    (
        ("otra", 1),
        ("otro", 1),
        ("otra mascota", 2),
        ("es para otra mascota", 1),
        ("ninguna de esas", 3),
        ("quiero registrar otra", 1),
        ("no, otro", 1),
        ("2", 1),
        ("4", 3),
    ),
)
def test_recognizes_new_pet_selection(message: str, count: int) -> None:
    assert wants_to_register_another_pet(message, count) is True


@pytest.mark.parametrize(
    ("message", "count"),
    (
        ("1", 1),
        ("Milou", 1),
        ("otro horario", 1),
        ("No quiero registrar otra mascota", 1),
        ("Prefiero no registrar otra mascota", 1),
        ("No registrar otra mascota", 1),
        ("", 1),
        ("3", 1),
    ),
)
def test_rejects_messages_that_do_not_select_a_new_pet(
    message: str, count: int
) -> None:
    assert wants_to_register_another_pet(message, count) is False


def test_rejects_negative_existing_pet_count() -> None:
    with pytest.raises(ValueError, match="existing pet count cannot be negative"):
        wants_to_register_another_pet("otra", -1)
