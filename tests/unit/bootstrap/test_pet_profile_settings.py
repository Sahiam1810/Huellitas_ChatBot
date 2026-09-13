import pytest
from pydantic import ValidationError

from app.bootstrap.settings import Settings


def test_backend_configuration_is_optional_by_default() -> None:
    settings = Settings(environment="test", _env_file=None)

    assert settings.active_backend_configuration() is None
    assert settings.appointment_booking_ttl_seconds == 300
    assert settings.appointment_availability_search_days == 14
    assert settings.appointment_availability_max_dates == 3


def test_enabled_backend_requires_an_http_base_url() -> None:
    with pytest.raises(ValidationError, match="Backend base URL"):
        Settings(backend_enabled=True, backend_base_url=None, _env_file=None)


def test_appointment_availability_limits_load_from_environment(monkeypatch) -> None:
    monkeypatch.setenv("HUELLITAS_APPOINTMENT_AVAILABILITY_SEARCH_DAYS", "21")
    monkeypatch.setenv("HUELLITAS_APPOINTMENT_AVAILABILITY_MAX_DATES", "5")

    settings = Settings(environment="test", _env_file=None)

    assert settings.appointment_availability_search_days == 21
    assert settings.appointment_availability_max_dates == 5


@pytest.mark.parametrize(
    "field",
    [
        "appointment_availability_search_days",
        "appointment_availability_max_dates",
    ],
)
def test_appointment_availability_limits_reject_zero(field: str) -> None:
    with pytest.raises(ValidationError):
        Settings(environment="test", _env_file=None, **{field: 0})
