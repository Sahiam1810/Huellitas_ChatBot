from collections.abc import Callable, Iterator
from typing import Any

import pytest

from tests.support.jwt import (
    AUDIENCE,
    ISSUER,
    KEY_ID,
    TEST_JWT_KEYS,
    JwtTestKeyMaterial,
    issue_token,
)


@pytest.fixture(autouse=True)
def configure_test_jwt_environment(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    monkeypatch.setenv(
        "HUELLITAS_JWT_PUBLIC_KEY_PEM_BASE64",
        TEST_JWT_KEYS.public_key_pem_base64,
    )
    monkeypatch.setenv("HUELLITAS_JWT_ISSUER", ISSUER)
    monkeypatch.setenv("HUELLITAS_JWT_AUDIENCE", AUDIENCE)
    monkeypatch.setenv("HUELLITAS_JWT_KEY_ID", KEY_ID)
    monkeypatch.setenv("HUELLITAS_JWT_CLOCK_SKEW_SECONDS", "0")
    monkeypatch.setenv("HUELLITAS_KNOWLEDGE_ADMIN_ROLE", "Administrador")
    yield


@pytest.fixture
def jwt_key_material() -> JwtTestKeyMaterial:
    return TEST_JWT_KEYS


@pytest.fixture
def issue_access_token() -> Callable[..., str]:
    def issue(**overrides: Any) -> str:
        return issue_token(TEST_JWT_KEYS, **overrides)

    return issue


@pytest.fixture
def auth_headers(issue_access_token: Callable[..., str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token()}"}


@pytest.fixture
def admin_auth_headers(issue_access_token: Callable[..., str]) -> dict[str, str]:
    return {"Authorization": f"Bearer {issue_access_token(role='Administrador')}"}
