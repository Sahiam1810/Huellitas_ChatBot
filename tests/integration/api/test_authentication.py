from typing import Annotated

import pytest
from fastapi import Security
from fastapi.testclient import TestClient
from pydantic import SecretStr

from app.api.dependencies import get_authenticated_access, get_authenticated_principal
from app.bootstrap.application import create_application
from app.bootstrap.settings import Settings
from app.ports.token_validator import AuthenticatedPrincipal
from app.shared.exceptions import TokenValidatorConfigurationError
from tests.support.jwt import ACCOUNT_ID, PERSON_ID, create_key_material


def application_with_probe(settings: Settings | None = None):
    app = create_application(settings or Settings(environment="test", _env_file=None))

    @app.get("/authentication-probe", include_in_schema=False)
    def authentication_probe(
        principal: Annotated[AuthenticatedPrincipal, Security(get_authenticated_principal)],
    ) -> dict[str, str]:
        return {
            "accountId": str(principal.account_id),
            "personId": str(principal.person_id),
            "role": principal.role,
        }

    @app.get("/authenticated-access-probe", include_in_schema=False)
    def authenticated_access_probe(
        access: Annotated[object, Security(get_authenticated_access)],
    ) -> dict[str, str]:
        return {
            "personId": str(access.principal.person_id),
            "bearerToken": access.bearer_token,
        }

    return app


def test_health_and_info_remain_public() -> None:
    with TestClient(create_application(Settings(environment="test", _env_file=None))) as client:
        live = client.get("/health/live")
        info = client.get("/api/v1/info")

    assert live.status_code == 200
    assert info.status_code == 200


def test_valid_bearer_token_resolves_authenticated_principal(
    auth_headers: dict[str, str],
) -> None:
    with TestClient(application_with_probe()) as client:
        response = client.get("/authentication-probe", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "accountId": str(ACCOUNT_ID),
        "personId": str(PERSON_ID),
        "role": "Cliente",
    }


def test_valid_bearer_is_retained_only_in_authenticated_request_access(
    auth_headers: dict[str, str],
) -> None:
    expected_token = auth_headers["Authorization"].removeprefix("Bearer ")

    with TestClient(application_with_probe()) as client:
        response = client.get("/authenticated-access-probe", headers=auth_headers)

    assert response.status_code == 200
    assert response.json() == {
        "personId": str(PERSON_ID),
        "bearerToken": expected_token,
    }


def test_missing_bearer_returns_safe_problem_details() -> None:
    with TestClient(application_with_probe()) as client:
        response = client.get("/authentication-probe")

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["code"] == "authentication_required"
    assert response.json()["instance"] == "/authentication-probe"


def test_invalid_bearer_returns_safe_problem_details() -> None:
    with TestClient(application_with_probe()) as client:
        response = client.get(
            "/authentication-probe",
            headers={"Authorization": "Bearer secret-token-that-must-not-leak"},
        )

    assert response.status_code == 401
    assert response.headers["content-type"].startswith("application/problem+json")
    assert response.headers["www-authenticate"] == "Bearer"
    assert response.json()["code"] == "invalid_access_token"
    assert "secret-token-that-must-not-leak" not in response.text


def test_application_rejects_missing_jwt_public_key() -> None:
    settings = Settings(
        environment="test",
        jwt_public_key_pem_base64=None,
        _env_file=None,
    )

    with pytest.raises((TokenValidatorConfigurationError, ValueError)):
        create_application(settings)


def test_application_rejects_weak_jwt_public_key() -> None:
    weak_keys = create_key_material(key_size=1024)
    settings = Settings(
        environment="test",
        jwt_public_key_pem_base64=SecretStr(weak_keys.public_key_pem_base64),
        _env_file=None,
    )

    with pytest.raises(TokenValidatorConfigurationError):
        create_application(settings)
