import pytest
from pydantic import ValidationError

from app.bootstrap.settings import Settings


def test_backend_configuration_is_optional_by_default() -> None:
    settings = Settings(environment="test", _env_file=None)

    assert settings.active_backend_configuration() is None


def test_enabled_backend_requires_an_http_base_url() -> None:
    with pytest.raises(ValidationError, match="Backend base URL"):
        Settings(backend_enabled=True, backend_base_url=None, _env_file=None)
