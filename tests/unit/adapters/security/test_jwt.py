from base64 import b64encode
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import ec
from pydantic import SecretStr

from app.adapters.security.jwt import JwtRs256TokenValidator
from app.bootstrap.settings import ActiveJwtConfiguration
from app.shared.exceptions import InvalidAccessTokenError, TokenValidatorConfigurationError
from tests.support.jwt import (
    ACCOUNT_ID,
    AUDIENCE,
    ISSUER,
    KEY_ID,
    PERSON_ID,
    ROLE_ID,
    JwtTestKeyMaterial,
    create_key_material,
    issue_token,
)


def configuration(
    keys: JwtTestKeyMaterial,
    **overrides: Any,
) -> ActiveJwtConfiguration:
    values: dict[str, Any] = {
        "public_key_pem_base64": SecretStr(keys.public_key_pem_base64),
        "issuer": ISSUER,
        "audience": AUDIENCE,
        "key_id": KEY_ID,
        "clock_skew_seconds": 0,
        "knowledge_admin_role": "Administrador",
    }
    values.update(overrides)
    return ActiveJwtConfiguration(**values)


def reissue(
    token: str,
    keys: JwtTestKeyMaterial,
    *,
    claim_overrides: dict[str, Any] | None = None,
    remove_claim: str | None = None,
    key_id: str | None = KEY_ID,
    signing_keys: JwtTestKeyMaterial | None = None,
) -> str:
    payload = jwt.decode(token, options={"verify_signature": False})
    if claim_overrides:
        payload.update(claim_overrides)
    if remove_claim:
        payload.pop(remove_claim)
    headers = {} if key_id is None else {"kid": key_id}
    signer = signing_keys or keys
    return jwt.encode(payload, signer.private_key, algorithm="RS256", headers=headers)


def test_valid_backend_token_maps_authenticated_principal(
    jwt_key_material: JwtTestKeyMaterial,
) -> None:
    validator = JwtRs256TokenValidator(configuration(jwt_key_material))

    principal = validator.validate(issue_token(jwt_key_material))

    assert principal.account_id == ACCOUNT_ID
    assert principal.person_id == PERSON_ID
    assert principal.role_id == ROLE_ID
    assert principal.role == "Cliente"
    assert principal.username == "cliente.demo"
    assert principal.email == "cliente@example.test"


@pytest.mark.parametrize(
    "public_key",
    [
        SecretStr("%%%"),
        SecretStr(b64encode(b"not a PEM key").decode("ascii")),
    ],
)
def test_validator_rejects_invalid_public_key_material(
    jwt_key_material: JwtTestKeyMaterial,
    public_key: SecretStr,
) -> None:
    with pytest.raises(TokenValidatorConfigurationError):
        JwtRs256TokenValidator(configuration(jwt_key_material, public_key_pem_base64=public_key))


def test_validator_rejects_non_rsa_public_key(
    jwt_key_material: JwtTestKeyMaterial,
) -> None:
    ec_public_pem = (
        ec.generate_private_key(ec.SECP256R1())
        .public_key()
        .public_bytes(
            serialization.Encoding.PEM,
            serialization.PublicFormat.SubjectPublicKeyInfo,
        )
    )

    with pytest.raises(TokenValidatorConfigurationError):
        JwtRs256TokenValidator(
            configuration(
                jwt_key_material,
                public_key_pem_base64=SecretStr(b64encode(ec_public_pem).decode("ascii")),
            )
        )


def test_validator_rejects_rsa_keys_below_2048_bits() -> None:
    weak_keys = create_key_material(key_size=1024)

    with pytest.raises(TokenValidatorConfigurationError):
        JwtRs256TokenValidator(configuration(weak_keys))


def test_validator_rejects_non_rs256_algorithm(
    jwt_key_material: JwtTestKeyMaterial,
) -> None:
    token = jwt.encode(
        {"sub": str(ACCOUNT_ID)},
        "symmetric-test-secret-with-enough-length",
        algorithm="HS256",
        headers={"kid": KEY_ID},
    )

    with pytest.raises(InvalidAccessTokenError):
        JwtRs256TokenValidator(configuration(jwt_key_material)).validate(token)


@pytest.mark.parametrize("key_id", [None, "another-key"])
def test_validator_rejects_missing_or_wrong_key_id(
    jwt_key_material: JwtTestKeyMaterial,
    key_id: str | None,
) -> None:
    token = reissue(issue_token(jwt_key_material), jwt_key_material, key_id=key_id)

    with pytest.raises(InvalidAccessTokenError):
        JwtRs256TokenValidator(configuration(jwt_key_material)).validate(token)


def test_validator_rejects_signature_from_another_key(
    jwt_key_material: JwtTestKeyMaterial,
) -> None:
    other_keys = create_key_material()
    token = reissue(
        issue_token(jwt_key_material),
        jwt_key_material,
        signing_keys=other_keys,
    )

    with pytest.raises(InvalidAccessTokenError):
        JwtRs256TokenValidator(configuration(jwt_key_material)).validate(token)


@pytest.mark.parametrize(
    "claim_overrides",
    [
        {"iss": "https://wrong-issuer.test"},
        {"aud": "wrong-audience"},
        {"exp": datetime.now(UTC) - timedelta(seconds=1)},
        {"nbf": datetime.now(UTC) + timedelta(minutes=5)},
        {"iat": datetime.now(UTC) + timedelta(minutes=5)},
    ],
)
def test_validator_rejects_invalid_registered_claims(
    jwt_key_material: JwtTestKeyMaterial,
    claim_overrides: dict[str, Any],
) -> None:
    token = reissue(
        issue_token(jwt_key_material),
        jwt_key_material,
        claim_overrides=claim_overrides,
    )

    with pytest.raises(InvalidAccessTokenError):
        JwtRs256TokenValidator(configuration(jwt_key_material)).validate(token)


@pytest.mark.parametrize(
    "claim",
    [
        "sub",
        "person_id",
        "role_id",
        "role",
        "preferred_username",
        "email",
        "jti",
        "iat",
        "nbf",
        "exp",
    ],
)
def test_validator_rejects_missing_required_claim(
    jwt_key_material: JwtTestKeyMaterial,
    claim: str,
) -> None:
    token = reissue(
        issue_token(jwt_key_material),
        jwt_key_material,
        remove_claim=claim,
    )

    with pytest.raises(InvalidAccessTokenError):
        JwtRs256TokenValidator(configuration(jwt_key_material)).validate(token)


@pytest.mark.parametrize("claim", ["sub", "person_id", "role_id", "jti"])
def test_validator_rejects_non_uuid_identity_claims(
    jwt_key_material: JwtTestKeyMaterial,
    claim: str,
) -> None:
    token = reissue(
        issue_token(jwt_key_material),
        jwt_key_material,
        claim_overrides={claim: "not-a-uuid"},
    )

    with pytest.raises(InvalidAccessTokenError):
        JwtRs256TokenValidator(configuration(jwt_key_material)).validate(token)


@pytest.mark.parametrize("claim", ["role", "preferred_username", "email"])
def test_validator_rejects_blank_text_identity_claims(
    jwt_key_material: JwtTestKeyMaterial,
    claim: str,
) -> None:
    token = reissue(
        issue_token(jwt_key_material),
        jwt_key_material,
        claim_overrides={claim: " "},
    )

    with pytest.raises(InvalidAccessTokenError):
        JwtRs256TokenValidator(configuration(jwt_key_material)).validate(token)
